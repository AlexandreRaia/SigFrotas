from django.urls import include, path

urlpatterns = [
    path('', include('apps.core.urls')),
    path('', include('apps.financeiro.urls')),
    path('', include('apps.frota.urls')),
    path('', include('apps.pessoas.urls')),
    path('', include('apps.manutencao.urls')),
    path('importacao/', include('apps.importacao.urls')),
]
