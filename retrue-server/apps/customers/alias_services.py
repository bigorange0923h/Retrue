"""客户别称维护：按康复师归一化、冲突校验和审计，不猜测身份。"""

from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError

from apps.audit.models import AuditAction, write_audit_log
from apps.customers.catalog import normalize_name
from apps.customers.models import Customer, CustomerAlias
from apps.customers.serializers import CustomerAliasSerializer


def _check_alias(therapist, customer: Customer, alias: str, is_active: bool, alias_id=None) -> str:
    """校验同账号别称唯一与正式名歧义；停用别称继续保留匹配键供追溯。"""
    normalized = normalize_name(alias)
    existing = CustomerAlias.objects.filter(therapist=therapist, normalized_alias=normalized)
    if alias_id is not None:
        existing = existing.exclude(id=alias_id)
    if existing.exists():
        raise ValidationError("该别称已存在，请编辑原别称或使用其他称呼")
    if is_active:
        names = Customer.objects.filter(therapist=therapist).exclude(id=customer.id).values_list("name", flat=True)
        if any(normalize_name(name) == normalized for name in names):
            raise ValidationError("别称与其他客户正式名冲突，请使用不会产生歧义的称呼")
    return normalized


def save_alias(therapist, customer: Customer, data: dict, alias: CustomerAlias | None = None) -> CustomerAlias:
    """原子增改别称并审计；数据库唯一冲突转换为安全的字段错误。"""
    try:
        with transaction.atomic():
            before = dict(CustomerAliasSerializer(alias).data) if alias is not None else None
            alias_text = data.get("alias", alias.alias if alias is not None else "")
            is_active = data.get("is_active", alias.is_active if alias is not None else True)
            normalized = _check_alias(therapist, customer, alias_text, is_active, alias.id if alias else None)
            if alias is None:
                alias = CustomerAlias.objects.create(therapist=therapist, customer=customer,
                                                      alias=alias_text, normalized_alias=normalized, is_active=is_active)
            else:
                alias.alias, alias.normalized_alias, alias.is_active = alias_text, normalized, is_active
                alias.save(update_fields=["alias", "normalized_alias", "is_active"])
            write_audit_log(actor=therapist, action=AuditAction.UPDATE if before else AuditAction.CREATE,
                            obj=alias, before=before, after=dict(CustomerAliasSerializer(alias).data),
                            reason="维护客户别称")
            return alias
    except IntegrityError as exc:
        raise ValidationError("该别称已存在，请刷新后重试") from exc
