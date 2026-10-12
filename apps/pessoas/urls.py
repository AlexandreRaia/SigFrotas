from django.urls import path

from apps.core.urls import caminhos

from . import views

ROTAS = dict(views.ROTAS)
ROTAS['motoristas'] = dict(
    ROTAS['motoristas'],
    novo=views.MotoristaNovo.as_view(model=views.Motorista, form_class=views.MotoristaForm, base='motoristas',
                                     titulo='Novo: motorista', permissao=views.GERIR),
    editar=views.MotoristaEditar.as_view(model=views.Motorista, form_class=views.MotoristaForm, base='motoristas',
                                         titulo='Editar: motorista', permissao=views.GERIR),
)

urlpatterns = []
for base, rotas in ROTAS.items():
    urlpatterns += caminhos(base, rotas)
urlpatterns += [
    path('motoristas/<int:pk>/', views.MotoristaDetalhe.as_view(), name='motoristas_detalhe'),
    path('motoristas/<int:pk>/certificados/novo/', views.CertificadoNovo.as_view(), name='motoristas_certificado_novo'),
    path('motoristas/<int:pk>/certificados/<int:item_pk>/excluir/', views.CertificadoExcluir.as_view(), name='motoristas_certificado_excluir'),
    path('motoristas/<int:pk>/afastamentos/novo/', views.AfastamentoNovo.as_view(), name='motoristas_afastamento_novo'),
    path('motoristas/<int:pk>/afastamentos/<int:item_pk>/excluir/', views.AfastamentoExcluir.as_view(), name='motoristas_afastamento_excluir'),
    path('motoristas/<int:pk>/penalidades/nova/', views.PenalidadeNova.as_view(), name='motoristas_penalidade_nova'),
    path('motoristas/<int:pk>/anexos/novo/', views.AnexoNovo.as_view(), name='motoristas_anexo_novo'),
]
