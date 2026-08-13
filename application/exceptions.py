from typing import Any


class ApplicationError(Exception):
    """Базовое исключение для всех ошибок прикладного слоя."""

    def __init__(self, message: str = "Произошла ошибка прикладного уровня") -> None:
        self.message = message
        super().__init__(self.message)


class NotFoundError(ApplicationError):
    """Ресурс или сущность не найдена."""

    def __init__(self, entity_name: str, entity_id: Any) -> None:
        self.entity_name = entity_name
        self.entity_id = entity_id
        super().__init__(f"Сущность {entity_name} с ID '{entity_id}' не найдена.")


class ApplicationValidationError(ApplicationError):
    """Ошибка валидации данных на уровне сценария использования (Use Case)."""

    def __init__(self, message: str = "Ошибка валидации входных данных") -> None:
        super().__init__(message)


class ExternalServiceError(ApplicationError):
    """Ошибка при обращении к внешним сервисам (LLM, Векторные БД и т.д.)."""

    def __init__(self, service_name: str, details: str) -> None:
        self.service_name = service_name
        self.details = details
        super().__init__(f"Ошибка сервиса '{service_name}': {details}")


class OutboxPublishError(ApplicationError):
    """Ошибка при публикациях сообщений из Outbox."""

    def __init__(self, message_id: str, reason: str) -> None:
        self.message_id = message_id
        self.reason = reason
        super().__init__(f"Не удалось опубликовать Outbox-сообщение [{message_id}]: {reason}")