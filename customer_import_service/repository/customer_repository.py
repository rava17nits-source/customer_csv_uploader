from __future__ import annotations

import uuid

from django.db import IntegrityError, transaction
from django.db.models import Q

from customer_import_service.db.models import Customer
from customer_import_service.errors import APIError


def list_customers(filters: dict) -> object:
    qs = Customer.objects.all().order_by("-updated_at")
    if filters.get("email"):
        qs = qs.filter(email=filters["email"].strip().lower())
    if filters.get("status"):
        qs = qs.filter(status=filters["status"].strip().lower())
    if filters.get("tier"):
        qs = qs.filter(tier=filters["tier"].strip().lower())
    if filters.get("q"):
        query = filters["q"].strip()
        qs = qs.filter(Q(name__icontains=query) | Q(email__icontains=query))
    return qs


def create_customer(cleaned: dict, actor: str) -> Customer:
    try:
        with transaction.atomic():
            customer = Customer.objects.create(
                p=cleaned.get("p") or None,
                cid=cleaned.get("cid") or None,
                email=cleaned["email"],
                name=cleaned["name"],
                status=cleaned["status"],
                tier=cleaned["tier"],
                tags=cleaned.get("tags", ""),
                note=cleaned.get("note", ""),
                internal_note=cleaned.get("internal_note", ""),
                source_updated_at=cleaned["source_updated_at"],
                created_by=actor,
                updated_by=actor,
            )
            return customer
    except IntegrityError as exc:
        raise APIError(409, "customer_conflict", "Customer email already exists.") from exc


def _customer_uuid(customer_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(customer_id))
    except (TypeError, ValueError) as exc:
        raise APIError(400, "bad_uuid", "Customer ID must be a valid UUID.") from exc


def get_customer(customer_id: str) -> Customer:
    customer_uuid = _customer_uuid(customer_id)
    try:
        return Customer.objects.get(pk=customer_uuid)
    except Customer.DoesNotExist as exc:
        raise APIError(404, "customer_not_found", "Customer was not found.") from exc


def update_customer(customer: Customer, cleaned: dict, actor: str) -> Customer:
    if "email" in cleaned and Customer.objects.exclude(pk=customer.pk).filter(email=cleaned["email"]).exists():
        raise APIError(409, "email_conflict", "email is already attached to another customer.")
    candidate_p = cleaned.get("p", customer.p)
    candidate_cid = cleaned.get("cid", customer.cid)
    if (("p" in cleaned) or ("cid" in cleaned)) and Customer.objects.exclude(pk=customer.pk).filter(p=candidate_p, cid=candidate_cid).exists():
        raise APIError(409, "customer_conflict", "partner and cid is already attached to another customer.")
    for field, value in cleaned.items():
        setattr(customer, field, value)
    customer.updated_by = actor
    customer.save()
    return customer


def deactivate_customer(customer: Customer, actor: str) -> None:
    customer.status = Customer.Status.INACTIVE
    customer.updated_by = actor
    customer.save(update_fields=["status", "updated_by", "updated_at"])


def count_customers() -> int:
    return Customer.objects.count()
