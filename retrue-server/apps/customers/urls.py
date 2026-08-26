"""customers：客户接口路由。"""

from django.urls import path

from apps.customers import views

urlpatterns = [
    path("", views.CustomerListView.as_view(), name="customer-list"),
    path("<int:customer_id>/", views.CustomerDetailView.as_view(), name="customer-detail"),
]
