"""HTTP API заказов с защищённой документацией и административными маршрутами."""

from contextlib import asynccontextmanager
from time import monotonic
from typing import Annotated
from uuid import UUID, uuid4
import logging

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload, sessionmaker

from . import crud
from .core import SessionDep, get_settings, make_engine, require_admin
from .models import Application, Service
from .schemas import ApplicationRead, ApplicationReceipt, ApplicationStatus, ApplicationWrite, ServiceRead, ServiceWrite

logger = logging.getLogger("customer_orders")


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = make_engine(settings)
        app.state.sessions = sessionmaker(engine, expire_on_commit=False)
        yield
        engine.dispose()

    app = FastAPI(
        title="Customer Orders API", version="0.2.0", docs_url=None, redoc_url=None,
        openapi_url=None, redirect_slashes=False, lifespan=lifespan,
    )

    @app.middleware("http")
    async def access_log(request: Request, call_next):
        started = monotonic()
        request_id = uuid4().hex
        try:
            response = await call_next(request)
        except Exception:
            logger.error("internal_error")
            response = JSONResponse(status_code=500, content={"detail": "Не удалось обработать запрос"})
        # Не записываем URL, IP, query, заголовки или введённые данные.
        logger.info("request_finished method=%s status=%s duration_ms=%d request_id=%s", request.method, response.status_code, (monotonic() - started) * 1000, request_id)
        response.headers["X-Request-ID"] = request_id
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        issues = []
        messages = {
            "missing": "Заполните обязательное поле", "int_type": "Укажите целое число",
            "int_parsing": "Укажите целое число", "string_too_short": "Значение слишком короткое",
            "string_too_long": "Значение слишком длинное", "extra_forbidden": "Неизвестное поле",
            "greater_than_equal": "Значение меньше допустимого", "less_than_equal": "Значение больше допустимого",
            "literal_error": "Выберите допустимое значение", "json_invalid": "Некорректный JSON",
        }
        for issue in error.errors():
            location = [str(part) for part in issue["loc"] if part not in ("body", "query")]
            message = messages.get(issue["type"], issue["msg"].removeprefix("Value error, "))
            if "email" in location:
                message = "Укажите корректный email"
            issues.append({"field": ".".join(location), "message": message})
        return JSONResponse(status_code=422, content={"detail": issues})

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, error: SQLAlchemyError):
        logger.error("database_unavailable")
        return JSONResponse(status_code=503, content={"detail": "Сервис временно недоступен. Попробуйте позже."})

    @app.exception_handler(Exception)
    async def internal_error(request: Request, error: Exception):
        logger.error("internal_error")
        return JSONResponse(status_code=500, content={"detail": "Не удалось обработать запрос"})

    public = APIRouter(prefix="/api", tags=["Публичный API"])

    @public.get("/health")
    def health(session: SessionDep):
        session.execute(text("SELECT 1"))
        return {"status": "ok", "component": "backend", "version": settings.app_version, "release": settings.release_id}

    @public.get("/services", response_model=list[ServiceRead])
    def services(session: SessionDep):
        return crud.list_services(session)

    @public.post("/applications", response_model=ApplicationReceipt, status_code=201)
    def applications(data: ApplicationWrite, session: SessionDep, response: Response, idempotency_key: Annotated[UUID | None, Header()] = None):
        application_id, created = crud.create_application(session, data, idempotency_key or uuid4())
        response.status_code = 201 if created else 200
        return ApplicationReceipt(id=application_id)

    admin = APIRouter(prefix="/api/admin", tags=["Администрирование"], dependencies=[Depends(require_admin)])

    @admin.get("/services", response_model=list[ServiceRead])
    def all_services(session: SessionDep):
        return crud.list_services(session, include_inactive=True)

    @admin.post("/services", response_model=ServiceRead, status_code=201)
    def add_service(data: ServiceWrite, session: SessionDep):
        return crud.write_service(session, data)

    @admin.get("/services/{service_id}", response_model=ServiceRead)
    def get_service(service_id: int, session: SessionDep):
        service = session.get(Service, service_id)
        if service is None:
            raise HTTPException(404, "Услуга не найдена")
        return service

    @admin.put("/services/{service_id}", response_model=ServiceRead)
    def update_service(service_id: int, data: ServiceWrite, session: SessionDep):
        return crud.write_service(session, data, service_id)

    @admin.delete("/services/{service_id}", status_code=204)
    def delete_service(service_id: int, session: SessionDep):
        with session.begin():
            service = session.get(Service, service_id)
            if service is None:
                raise HTTPException(404, "Услуга не найдена")
            service.is_active = False
        return Response(status_code=204)

    @admin.get("/applications", response_model=list[ApplicationRead])
    def all_applications(session: SessionDep, offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=100)] = 25):
        return list(session.scalars(select(Application).options(selectinload(Application.metrics)).order_by(Application.created_at.desc()).offset(offset).limit(limit)))

    @admin.get("/applications/{application_id}", response_model=ApplicationRead)
    def application(application_id: UUID, session: SessionDep):
        return crud.get_application(session, application_id)

    @admin.patch("/applications/{application_id}", response_model=ApplicationRead)
    def update_application(application_id: UUID, data: ApplicationStatus, session: SessionDep):
        with session.begin():
            record = crud.get_application(session, application_id)
            record.status = data.status
        return record

    @admin.delete("/applications/{application_id}", status_code=204)
    def delete_application(application_id: UUID, session: SessionDep):
        with session.begin():
            record = crud.get_application(session, application_id)
            session.delete(record)
        return Response(status_code=204)

    @admin.get("/docs", include_in_schema=False)
    def swagger():
        return get_swagger_ui_html(
            openapi_url="/api/admin/openapi.json", title="Customer Orders API",
            swagger_js_url="/assets/swagger/swagger-ui-bundle.js",
            swagger_css_url="/assets/swagger/swagger-ui.css", swagger_favicon_url="/favicon.svg",
            swagger_ui_parameters={"persistAuthorization": False, "displayRequestDuration": True, "validatorUrl": None},
        )

    @admin.get("/openapi.json", include_in_schema=False)
    def openapi():
        return app.openapi()

    app.include_router(public)
    app.include_router(admin)
    return app


app = create_app()
