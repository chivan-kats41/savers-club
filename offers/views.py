from decimal import Decimal, InvalidOperation

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.permissions import IsRole
from core.models import Area
from merchants.models import Merchant

from .merchant_services import OfferError, create_offer, delete_offer, pause_offer, update_offer
from .models import Offer, OfferCategory
from .serializers import MerchantOfferSerializer, OfferCategorySerializer, PublicOfferSerializer

IsMerchant = IsRole.for_roles("merchant")
IsMember = IsRole.for_roles("member")


def _error(code, exc, status=400):
    message = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
    return Response({"success": False, "error": {"code": code, "message": message, "details": {}}}, status=status)


def _extract_offer_fields(data):
    fields = {}
    if "category_id" in data or "category" in data:
        category = OfferCategory.objects.filter(pk=data.get("category_id") or data.get("category")).first()
        if category:
            fields["category"] = category
    if "area_id" in data or "area" in data:
        area = Area.objects.filter(pk=data.get("area_id") or data.get("area")).first()
        if area:
            fields["area"] = area
    for text_field in ("item_name", "pickup_location", "packaging_status"):
        if text_field in data:
            fields[text_field] = data[text_field]
    for decimal_field in ("normal_price", "member_price", "offer_radius_km"):
        if decimal_field in data and data[decimal_field] not in (None, ""):
            try:
                fields[decimal_field] = Decimal(str(data[decimal_field]))
            except InvalidOperation:
                pass
    if "quantity" in data:
        try:
            fields["quantity"] = int(data["quantity"])
        except (TypeError, ValueError):
            pass
    if "delivery_available" in data:
        fields["delivery_available"] = str(data["delivery_available"]).strip().lower() in ("1", "true", "yes", "on")
    if "expires_at" in data:
        from django.utils.dateparse import parse_datetime

        value = data["expires_at"]
        if isinstance(value, str):
            parsed = parse_datetime(value)
            if parsed is not None:
                fields["expires_at"] = parsed
        else:
            fields["expires_at"] = value
    return fields


class MerchantOffersView(APIView):
    """GET/POST /api/v1/merchant/offers/"""

    permission_classes = [IsAuthenticated, IsMerchant]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "write"
    serializer_class = MerchantOfferSerializer

    def get(self, request):
        merchant = get_object_or_404(Merchant, user=request.user)
        offers = Offer.objects.filter(merchant=merchant)
        return Response({"success": True, "data": MerchantOfferSerializer(offers, many=True).data})

    def post(self, request):
        merchant = get_object_or_404(Merchant, user=request.user)
        fields = _extract_offer_fields(request.data)
        missing = {"category", "area", "item_name", "normal_price", "member_price", "expires_at"} - fields.keys()
        if missing:
            return Response(
                {"success": False, "error": {"code": "MISSING_FIELDS", "message": f"Missing: {', '.join(sorted(missing))}", "details": {}}},
                status=400,
            )
        try:
            offer = create_offer(merchant, **fields)
        except OfferError as exc:
            return _error("OFFER_CREATE_FAILED", exc)
        return Response({"success": True, "data": MerchantOfferSerializer(offer).data}, status=201)


class MerchantOfferDetailView(APIView):
    """PATCH/DELETE /api/v1/merchant/offers/<id>/"""

    permission_classes = [IsAuthenticated, IsMerchant]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "write"
    serializer_class = MerchantOfferSerializer

    def patch(self, request, offer_id):
        merchant = get_object_or_404(Merchant, user=request.user)
        fields = _extract_offer_fields(request.data)
        try:
            offer = update_offer(merchant, offer_id, **fields)
        except OfferError as exc:
            return _error("OFFER_UPDATE_FAILED", exc)
        return Response({"success": True, "data": MerchantOfferSerializer(offer).data})

    def delete(self, request, offer_id):
        merchant = get_object_or_404(Merchant, user=request.user)
        try:
            delete_offer(merchant, offer_id)
        except OfferError as exc:
            return _error("OFFER_DELETE_FAILED", exc)
        return Response({"success": True, "data": None}, status=204)


class PauseOfferView(APIView):
    permission_classes = [IsAuthenticated, IsMerchant]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "write"
    serializer_class = MerchantOfferSerializer

    def post(self, request, offer_id):
        merchant = get_object_or_404(Merchant, user=request.user)
        try:
            offer = pause_offer(merchant, offer_id)
        except OfferError as exc:
            return _error("OFFER_PAUSE_FAILED", exc)
        return Response({"success": True, "data": MerchantOfferSerializer(offer).data})


class OfferCategoriesView(APIView):
    """GET /api/v1/offers/categories/ — any authenticated user."""

    permission_classes = [IsAuthenticated]
    serializer_class = OfferCategorySerializer

    def get(self, request):
        categories = OfferCategory.objects.filter(is_active=True)
        return Response({"success": True, "data": OfferCategorySerializer(categories, many=True).data})


class NearbyOffersView(APIView):
    """GET /api/v1/member/offers/nearby/?area_id=&category_id=&sort=

    "Nearby" here means area-based (matches this codebase's data model —
    Offer.area is a FK to core.Area, not a lat/lng point), per the spec's
    documented fallback when PostGIS isn't available. sort options:
    cheapest (default), biggest_saving, newest.
    """

    permission_classes = [IsAuthenticated, IsMember]
    serializer_class = PublicOfferSerializer

    def get(self, request):
        offers = Offer.objects.filter(status=Offer.Status.ACTIVE, expires_at__gt=timezone.now(), quantity__gt=0)

        area_id = request.query_params.get("area_id")
        if area_id:
            offers = offers.filter(area_id=area_id)

        category_id = request.query_params.get("category_id")
        if category_id:
            offers = offers.filter(category_id=category_id)

        search = request.query_params.get("q")
        if search:
            offers = offers.filter(item_name__icontains=search)

        sort = request.query_params.get("sort", "cheapest")
        if sort == "biggest_saving":
            offers = sorted(offers, key=lambda o: o.possible_saving, reverse=True)
        elif sort == "newest":
            offers = offers.order_by("-created_at")
        else:
            offers = offers.order_by("member_price")

        return Response({"success": True, "data": PublicOfferSerializer(offers, many=True).data})
