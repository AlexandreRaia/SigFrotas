from django.urls import path

from . import views


def caminhos(base, rotas, prefixo=None):
    """Urls de um cadastro gerado por views.rotas_cadastro: <base>_lista, _novo, _editar e (se houver) _alternar."""
    prefixo = prefixo or base.replace('_', '-')
    resultado = [
        path(f'{prefixo}/', rotas['lista'], name=f'{base}_lista'),
        path(f'{prefixo}/novo/', rotas['novo'], name=f'{base}_novo'),
        path(f'{prefixo}/<int:pk>/editar/', rotas['editar'], name=f'{base}_editar'),
    ]
    if 'alternar' in rotas:
        resultado.append(path(f'{prefixo}/<int:pk>/alternar/', rotas['alternar'], name=f'{base}_alternar'))
    return resultado


urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('entrar/', views.entrar, name='entrar'),
    path('sair/', views.sair, name='sair'),
    path('usuarios/<int:pk>/senha/', views.RedefinirSenha.as_view(), name='usuarios_senha'),
    path('auditoria/', views.ListaAuditoria.as_view(), name='auditoria'),
    path('anexos/<int:pk>/', views.baixar_anexo, name='anexo_baixar'),
    path('notificacoes/', views.ListaNotificacoes.as_view(), name='notificacoes'),
    path('notificacoes/ler-todas/', views.ler_todas_notificacoes, name='notificacoes_ler_todas'),
    path('notificacoes/<int:pk>/abrir/', views.abrir_notificacao, name='notificacao_abrir'),
]

for base, rotas in views.CADASTROS.items():
    urlpatterns += caminhos(base, rotas, prefixo=base)
