"""ioTec's RequestStatus enum -> what we do about it.

Spec: Pending, SentToVendor, Success, Failed, AwaitingApproval, RolledBack, Scheduled, Cancelled, Rejected.
Anything not listed here is treated as "still in progress": we never fail or credit on a status we don't know.
"""
SUCCESS = "success"
FAILED = "failed"
SENT = "sent_to_vendor"
IN_PROGRESS = "in_progress"

_MAP = {
    "success": SUCCESS,
    "failed": FAILED,
    "rolledback": FAILED,
    "cancelled": FAILED,
    "canceled": FAILED,
    "rejected": FAILED,
    "senttovendor": SENT,
    "pending": IN_PROGRESS,
    "awaitingapproval": IN_PROGRESS,
    "scheduled": IN_PROGRESS,
}


def classify(provider_status) -> str:
    key = str(provider_status or "").strip().lower().replace("_", "").replace(" ", "")
    return _MAP.get(key, IN_PROGRESS)
