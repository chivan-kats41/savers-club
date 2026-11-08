from django.conf import settings
from django.core.checks import Tags, Warning, register


@register(Tags.security, deploy=True)
def sms_configured(app_configs, **kwargs):
    """`manage.py check --deploy` warns if production would not be able to send SMS (OTPs!)."""
    if settings.SMS_GATEWAY_CLASS.endswith("ConsoleSMSGateway"):
        return [Warning("SMS_GATEWAY_CLASS is the console stub: users will not receive OTP codes or SMS notifications.",
                        hint="Set SMS_GATEWAY_CLASS=notifications.services.sms_gateway.IoTecSMSGateway.", id="notifications.W001")]
    if settings.SMS_GATEWAY_CLASS.endswith("IoTecSMSGateway") and not (
        settings.IOTEC_MESSAGING_CLIENT_ID and settings.IOTEC_MESSAGING_API_KEY
    ):
        return [Warning("ioTec Messaging credentials are missing: OTP codes and SMS will fail.",
                        hint="Set IOTEC_MESSAGING_CLIENT_ID and IOTEC_MESSAGING_API_KEY (messaging.iotec.io > Settings > CONFIGURATION).",
                        id="notifications.W002")]
    return []
