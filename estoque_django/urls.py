from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from django.templatetags.static import static as static_url
from django.views.generic import RedirectView
from django.urls import re_path
from django.views.static import serve
import os

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

urlpatterns += [
    re_path(
        r"^media/comunicados/(?P<path>.*)$",
        serve,
        {
            "document_root": os.path.join(
                settings.MEDIA_ROOT,
                "comunicados",
            )
        },
        name="servir_arquivo_comunicado",
    ),
]