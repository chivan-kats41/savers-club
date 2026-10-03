from celery import shared_task

from .services.reconciliation import reconcile_all_pending_payments, reconcile_all_pending_withdrawals


@shared_task(name="payments.reconcile_pending_payments")
def reconcile_pending_payments_task():
    return reconcile_all_pending_payments()


@shared_task(name="payments.reconcile_pending_withdrawals")
def reconcile_pending_withdrawals_task():
    return reconcile_all_pending_withdrawals()
