from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.views.generic import RedirectView

from core import health

urlpatterns = [
    path('health/live/', health.live, name='health_live'),
    path('health/ready/', health.ready, name='health_ready'),
    path(
        'favicon.ico',
        RedirectView.as_view(url=f'{settings.STATIC_URL}images/favicon.svg', permanent=False),
    ),
    path('admin/', admin.site.urls),
    path('', include('estoque.urls')),
    path('accounts/login/', auth_views.LoginView.as_view(), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    #path('estoque/', include('estoque.urls')),
    path('insumos/', include('insumos.urls')),
    path('integracao/', include('integracao.urls')),
    path('auditorias/', include('auditorias.urls')),
    path('ordens-servico/', include('ordens_servico.urls')),
]

if settings.DEBUG:
    from django.conf.urls.static import static

    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
