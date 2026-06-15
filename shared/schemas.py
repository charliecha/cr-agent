from enum import Enum
from pydantic import BaseModel


class Severity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class Finding(BaseModel):
    file: str
    line_start: int
    line_end: int
    severity: Severity
    # "logic_bug" | "memory_leak" | "api_mismatch" | "security" | "style"
    category: str
    description: str
    suggestion: str


class CRReport(BaseModel):
    pr_url: str
    findings: list[Finding]
    summary: str
    # "approve" | "request_changes" | "block"
    verdict: str
