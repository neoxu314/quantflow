"""Alert channels."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class AlertMessage:
    title: str
    content: str
    level: str = "info"
    timestamp: Optional[str] = None
    
    def format_content(self) -> str:
        return f"[{self.level}] {self.title}\n\n{self.content}"


class AlertChannel(ABC):
    
    @abstractmethod
    def send(self, message: AlertMessage) -> bool:
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        pass


class LogAlertChannel(AlertChannel):
    
    def __init__(self, level: str = "INFO"):
        self.level = level
    
    def get_name(self) -> str:
        return "Log"
    
    def send(self, message: AlertMessage) -> bool:
        import logging
        logger = logging.getLogger(__name__)
        
        logger.log(
            getattr(logging, self.level),
            f"[{message.title}] {message.content}"
        )
        return True