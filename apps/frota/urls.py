from django.urls import path

from apps.core.urls import caminhos

from . import views

ROTAS = dict(views.ROTAS)
ROTAS['veiculos'] = dict(
    ROTAS['veiculos'],
    lista=views.VeiculosLista.as_view(),
    novo=views.VeiculoNovo.as_view(model=views.Veiculo, form_class=views.VeiculoForm, base='veiculos',
                                   titulo='Novo: veículo', permissao=views.GERIR),
    editar=views.VeiculoEditar.as_view(model=views.Veiculo, form_class=views.VeiculoForm, base='veiculos',
                                       titulo='Editar: veículo', permissao=views.GERIR),
)

ROTAS['marcas'] = dict(ROTAS['marcas'], novo=views.MarcaNova.as_view(
    model=views.Marca, form_class=views.MarcaForm, base='marcas', titulo='Nova: marca', permissao=views.GERIR, catalogo_global=True))
ROTAS['modelos'] = dict(
    ROTAS['modelos'],
    novo=views.ModeloNovo.as_view(model=views.Modelo, form_class=views.ModeloForm, base='modelos', titulo='Novo: modelo',
                                  permissao=views.GERIR, catalogo_global=True, repassar_ao_novo=('marca',)),
    editar=views.ModeloEditar.as_view(model=views.Modelo, form_class=views.ModeloForm, base='modelos', titulo='Editar: modelo',
                                      permissao=views.GERIR, catalogo_global=True),
)

urlpatterns = []
for base, rotas in ROTAS.items():
    urlpatterns += caminhos(base, rotas)
urlpatterns += [
    path('veiculos/dados/', views.VeiculosDados.as_view(), name='veiculos_dados'),
    path('veiculos/<int:pk>/', views.VeiculoDetalhe.as_view(), name='veiculos_detalhe'),
    path('veiculos/<int:pk>/alternar-situacao/', views.VeiculoAlternarSituacao.as_view(), name='veiculos_alternar_situacao'),
    path('veiculos/<int:pk>/equipamentos/novo/', views.EquipamentoNovo.as_view(), name='veiculos_equipamento_novo'),
    path('veiculos/<int:pk>/equipamentos/<int:equipamento_pk>/excluir/', views.EquipamentoExcluir.as_view(),
         name='veiculos_equipamento_excluir'),
    path('veiculos/<int:pk>/leituras/nova/', views.LeituraNova.as_view(), name='veiculos_leitura_nova'),
    path('veiculos/<int:pk>/anexos/novo/', views.AnexoNovo.as_view(), name='veiculos_anexo_novo'),
]
