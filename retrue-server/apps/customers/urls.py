"""customers：客户接口路由。"""

from django.urls import path

from apps.customers import alias_views, lifecycle_views, views

urlpatterns = [
    path("", views.CustomerListView.as_view(), name="customer-list"),
    path("<int:customer_id>/", views.CustomerDetailView.as_view(), name="customer-detail"),
    path("<int:customer_id>/aliases/", alias_views.CustomerAliasListView.as_view(), name="customer-alias-list"),
    path("<int:customer_id>/aliases/<int:alias_id>/", alias_views.CustomerAliasDetailView.as_view(), name="customer-alias-detail"),
    path("<int:customer_id>/export/", lifecycle_views.CustomerExportView.as_view(), name="customer-export"),
    path("<int:customer_id>/deletion-preview/", lifecycle_views.CustomerDeletionPreviewView.as_view(), name="customer-deletion-preview"),
]
