"""Версионированная оценка по явным правилам, без внешней модели."""
import re

VERSION = 1


def evaluate(values, service_min=0, service_max=0):
    def field(name):
        return str(values.get(name) or "").lower()
    deadline = field("desired_deadline")
    reasons = []
    urgency, urgency_points = "unknown", 0
    # Не угадываем даты, свободные фразы с отрицанием и противоречивые сроки.
    if re.search(r"не\s+сроч|без\s+спеш|квартал|позже|[2-9]\s*месяц", deadline):
        urgency, urgency_points = "low", 5
    elif not re.search(r"не\s+(горит|спеш)", deadline):
        if re.search(r"срочно|сегодня|завтра|в течение недели|до недели|до 7 дней", deadline):
            urgency, urgency_points = "high", 50
        elif re.search(r"месяц|в течение 30 дней|2 недел|две недел|3 недел|три недел|4 недел", deadline):
            urgency, urgency_points = "medium", 25
        elif re.search(r"квартал|позже|не срочно|[2-9]\s*месяц", deadline):
            urgency, urgency_points = "low", 5
    if urgency == "unknown":
        reasons.append("Срок не определён правилами — требуется уточнение")
    else:
        reasons.append({"high": "Близкий срок запуска", "medium": "План запуска в течение месяца", "low": "Долгосрочный план"}[urgency])
    description = field("task_description")
    match = bool(re.search(r"crm|заяв|интеграц|бот|telegram|автомат|синхро|уведом|обмен данн", description))
    problem = bool(re.search(r"вручную|теря|дубл|ошиб|задерж|долго|не успев|проблем", description))
    outcome = bool(re.search(r"создава|собирать|передава|связать|настро|снизить|сократ|уведом|распредел|проверять", description))
    fit = 20 if match else 0
    readiness = (10 if problem else 0) + (10 if outcome else 0)
    budget = values.get("budget")
    if budget is not None and service_min <= budget <= service_max:
        readiness += 5
        reasons.append("Указан бюджет в диапазоне услуги")
    if re.search(r"собственник|директор|руководител|основател|owner|ceo", field("role")):
        readiness += 5
        reasons.append("Указана роль, связанная с принятием решения")
    if match:
        reasons.append("В описании есть признаки подходящего направления")
    if problem and outcome:
        reasons.append("Описаны проблема и желаемое действие")
    score = urgency_points + fit + readiness
    level = "high" if score >= 65 else "medium" if score >= 30 else "low"
    team = "Клиентские боты" if re.search(r"бот|telegram", description) else "Интеграции" if re.search(r"интеграц|crm|обмен данн|синхро", description) else "Автоматизация процессов" if match else "Первичная консультация"
    return {"version": VERSION, "score": score, "level": level, "urgency": urgency, "fit": "matched" if match else "clarify", "readiness": "high" if readiness >= 20 else "medium" if readiness >= 10 else "low", "reasons": reasons, "recommended_team": team, "personal_manager_recommended": level == "high"}


def assign(record, service):
    result = evaluate({name: getattr(record, name) for name in ("desired_deadline", "task_description", "budget", "role")}, service.budget_min, service.budget_max)
    record.priority_score = result["score"]
    record.priority_evaluation = result
