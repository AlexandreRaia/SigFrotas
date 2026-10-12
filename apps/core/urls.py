from django.urls import path

from . import views

urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('entrar/', views.entrar, name='entrar'),
    path('sair/', views.sair, name='sair'),
    path('usuarios/<int:pk>/senha/', views.RedefinirSenha.as_view(), name='usuarios_senha'),
    path('auditoria/', views.ListaAuditoria.as_view(), name='auditoria'),
    path('anexos/<int:pk>/', views.baixar_anexo, name='anexo_baixar'),
]

for base, rotas in views.CADASTROS.items():
    urlpatterns += [
        path(f'{base}/', rotas['lista'], name=f'{base}_lista'),
        path(f'{base}/novo/', rotas['novo'], name=f'{base}_novo'),
        path(f'{base}/<int:pk>/', rotas['editar'], name=f'{base}_editar'),
        path(f'{base}/<int:pk>/alternar/', rotas['alternar'], name=f'{base}_alternar'),
    ]
