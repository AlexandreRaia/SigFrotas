from django.urls import path

from apps.core.urls import caminhos

from . import views

ROTAS = dict(views.ROTAS)
ROTAS['veiculos'] = dict(
    ROTAS['veiculos'],
    novo=views.VeiculoNovo.as_view(model=views.Veiculo, form_class=views.VeiculoForm, base='veiculos',
                                   titulo='Novo: veículo', permissao=views.GERIR),
    editar=views.VeiculoEditar.as_view(model=views.Veiculo, form_class=views.VeiculoForm, base='veiculos',
                                       titulo='Editar: veículo', permissao=views.GERIR),
)

urlpatterns = []
for base, rotas in ROTAS.items():
    urlpatterns += caminhos(base, rotas)
urlpatterns += [
    path('veiculos/<int:pk>/', views.VeiculoDetalhe.as_view(), name='veiculos_detalhe'),
    path('veiculos/<int:pk>/equipamentos/novo/', views.EquipamentoNovo.as_view(), name='veiculos_equipamento_novo'),
    path('veiculos/<int:pk>/equipamentos/<int:equipamento_pk>/excluir/', views.EquipamentoExcluir.as_view(),
         name='veiculos_equipamento_excluir'),
    path('veiculos/<int:pk>/leituras/nova/', views.LeituraNova.as_view(), name='veiculos_leitura_nova'),
    path('veiculos/<int:pk>/anexos/novo/', views.AnexoNovo.as_view(), name='veiculos_anexo_novo'),
    path('marcas/', views.MarcasModelos.as_view(), name='marcas_lista'),
]
