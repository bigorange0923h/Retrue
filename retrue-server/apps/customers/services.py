"""customers：客户业务服务。

集中承载客户相关业务规则：数据隔离、手机号脱敏、审计记录。
View 只负责校验与响应，业务逻辑在此层实现。
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractUser

from apps.audit.models import AuditAction, write_audit_log
from apps.customers.models import Customer, mask_phone


def list_customers(
    therapist: AbstractUser,
    *,
    keyword: str = "",
    status: str = "",
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """分页查询当前康复师的客户。

    强制按 therapist 过滤实现数据隔离，支持姓名搜索与状态筛选。

    参数：
        therapist: 当前登录康复师用户。
        keyword: 姓名搜索关键字，可选。
        status: 客户状态筛选，可选。
        page: 页码，从 1 开始。
        page_size: 每页条数。
    返回：
        分页字典 {items, page, page_size, total}。
    """
    queryset = Customer.objects.filter(therapist=therapist)

    if keyword:
        queryset = queryset.filter(name__icontains=keyword)
    if status:
        queryset = queryset.filter(status=status)

    total = queryset.count()
    start = (page - 1) * page_size
    items = list(queryset[start : start + page_size])

    return {"items": items, "page": page, "page_size": page_size, "total": total}


def get_customer(therapist: AbstractUser, customer_id: int) -> Customer | None:
    """获取当前康复师的单个客户，校验归属。

    参数：
        therapist: 当前登录康复师用户。
        customer_id: 客户主键。
    返回：
        客户实例；不属于当前康复师或不存在时返回 None。
    """
    return Customer.objects.filter(therapist=therapist, id=customer_id).first()


def create_customer(therapist: AbstractUser, data: dict) -> Customer:
    """创建客户并记录审计。

    参数：
        therapist: 当前登录康复师用户。
        data: 客户字段数据。
    返回：
        新建的客户实例。
    """
    customer = Customer.objects.create(therapist=therapist, **data)
    write_audit_log(
        actor=therapist,
        action=AuditAction.CREATE,
        obj=customer,
        after=customer_to_dict(customer),
        reason="新建客户",
    )
    return customer


def update_customer(therapist: AbstractUser, customer: Customer, data: dict) -> Customer:
    """更新客户并记录审计（保留修改前后快照）。

    参数：
        therapist: 当前登录康复师用户。
        customer: 要更新的客户实例（须属于当前康复师）。
        data: 更新的字段数据。
    返回：
        更新后的客户实例。
    """
    before = customer_to_dict(customer)
    for field, value in data.items():
        if value is not None:
            setattr(customer, field, value)
    customer.save()
    write_audit_log(
        actor=therapist,
        action=AuditAction.UPDATE,
        obj=customer,
        before=before,
        after=customer_to_dict(customer),
        reason="更新客户资料",
    )
    return customer


def customer_to_dict(customer: Customer) -> dict:
    """将客户关键字段转为字典，用于审计快照。

    参数：
        customer: 客户实例。
    返回：
        含姓名、手机号（脱敏）、状态的字典。
    """
    return {
        "id": customer.id,
        "name": customer.name,
        "phone": mask_phone(customer.phone),
        "status": customer.status,
        "main_issue": customer.main_issue,
    }
