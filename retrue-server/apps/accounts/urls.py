"""accounts：认证接口路由。"""

from django.urls import path

from apps.accounts import views

urlpatterns = [
    # 登录在视图内自行执行 CSRF 校验（DRF as_view 默认豁免，见 LoginView.post）。
    path("login/", views.LoginView.as_view(), name="login"),
    path("csrf/", views.CsrfTokenView.as_view(), name="csrf-token"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("me/", views.CurrentUserView.as_view(), name="current-user"),
    path("users/", views.UserAdminListView.as_view(), name="user-admin-list"),
    path("users/<int:user_id>/", views.UserAdminDetailView.as_view(), name="user-admin-detail"),
]
