from django.urls import path

from apps.core.urls import caminhos
from apps.frota.models import Veiculo  # noqa: F401

from . import views
from .forms import ChamadoForm, SmvForm
from .models import Chamado, Smv

urlpatterns = []
for base, rotas in views.ROTAS.items():
    urlpatterns += caminhos(base, rotas)

urlpatterns += [
    # chamados
    path('chamados/', views.lista_chamados, name='chamados_lista'),
    path('chamados/novo/', views.ChamadoNovo.as_view(model=Chamado, form_class=ChamadoForm, base='chamados', titulo='Novo chamado',
                                                     permissao=views.ABRIR), name='chamados_novo'),
    path('chamados/<int:pk>/', views.ChamadoDetalhe.as_view(), name='chamados_detalhe'),
    path('chamados/<int:pk>/em-analise/', views.ChamadoEmAnalise.as_view(), name='chamados_em_analise'),
    path('chamados/<int:pk>/improcedente/', views.ChamadoImprocedente.as_view(), name='chamados_improcedente'),
    path('chamados/<int:pk>/cancelar/', views.ChamadoCancelar.as_view(), name='chamados_cancelar'),
    # SMV
    path('smv/', views.lista_smv, name='smv_lista'),
    path('smv/novo/', views.SmvNovo.as_view(model=Smv, form_class=SmvForm, base='smv', titulo='Nova SMV (entrada na oficina)',
                                            permissao=views.GERIR), name='smv_novo'),
    path('smv/<int:pk>/', views.SmvDetalhe.as_view(), name='smv_detalhe'),
    path('smv/<int:pk>/diagnostico/', views.SmvDiagnostico.as_view(), name='smv_diagnostico'),
    path('smv/<int:pk>/entrega/', views.SmvEntrega.as_view(), name='smv_entrega'),
    path('smv/<int:pk>/nota-fiscal/', views.SmvNotaFiscal.as_view(), name='smv_nota_fiscal'),
    path('smv/<int:pk>/conferir-nota/', views.SmvConferirNota.as_view(), name='smv_conferir_nota'),
    path('smv/<int:pk>/cancelar/', views.SmvCancelar.as_view(), name='smv_cancelar'),
    path('smv/<int:pk>/mensagens/', views.SmvMensagens.as_view(), name='smv_mensagens'),
    path('smv/<int:pk>/orcamento/novo/', views.SmvOrcamentoNovo.as_view(), name='smv_orcamento_novo'),
    # orcamentos
    path('orcamentos/', views.lista_orcamentos, name='orcamentos_lista'),
    path('orcamentos/<int:pk>/', views.OrcamentoDetalhe.as_view(), name='orcamentos_detalhe'),
    path('orcamentos/<int:pk>/itens/novo/', views.OrcamentoItemNovo.as_view(), name='orcamentos_item_novo'),
    path('orcamentos/<int:pk>/itens/<int:item_pk>/excluir/', views.OrcamentoItemExcluir.as_view(), name='orcamentos_item_excluir'),
    path('orcamentos/<int:pk>/enviar/', views.OrcamentoEnviar.as_view(), name='orcamentos_enviar'),
    path('orcamentos/<int:pk>/referencias/', views.OrcamentoReferencias.as_view(), name='orcamentos_referencias'),
    path('orcamentos/<int:pk>/analisar/', views.OrcamentoIniciarAnalise.as_view(), name='orcamentos_analisar'),
    path('orcamentos/<int:pk>/devolver/', views.OrcamentoDevolver.as_view(), name='orcamentos_devolver'),
    path('orcamentos/<int:pk>/empenho/', views.OrcamentoEmpenho.as_view(), name='orcamentos_empenho'),
    path('orcamentos/<int:pk>/assinar/', views.OrcamentoAssinar.as_view(), name='orcamentos_assinar'),
]
