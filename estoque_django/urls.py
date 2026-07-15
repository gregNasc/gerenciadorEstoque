from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from django.templatetags.static import static as static_url
from django.views.generic import RedirectView

urlpatterns = [
    path(
        'favicon.ico',
        RedirectView.as_view(url=static_url('images/favicon.svg'), permanent=False),
    ),
    path('admin/', admin.site.urls),
    path('', include('estoque.urls')),
    path('accounts/login/', auth_views.LoginView.as_view(), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    #path('estoque/', include('estoque.urls')),
    path('insumos/', include('insumos.urls')),
    path('integracao/', include('integracao.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
