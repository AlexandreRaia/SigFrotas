from django.urls import path

from apps.core.urls import caminhos

from . import views
from .models import Empenho  # noqa: F401

ROTAS = dict(views.ROTAS)
# empenho tem telas proprias de novo/editar (voltam para o detalhe)
ROTAS['empenhos'] = dict(
    ROTAS['empenhos'],
    novo=views.EmpenhoNovo.as_view(model=views.Empenho, form_class=views.EmpenhoForm, base='empenhos',
                                   titulo='Novo: empenho', permissao=views.GERIR),
    editar=views.EmpenhoEditar.as_view(model=views.Empenho, form_class=views.EmpenhoForm, base='empenhos',
                                       titulo='Editar: empenho', permissao=views.GERIR),
)

urlpatterns = []
for base, rotas in ROTAS.items():
    urlpatterns += caminhos(base, rotas)
urlpatterns += [
    path('empenhos/<int:pk>/', views.EmpenhoDetalhe.as_view(), name='empenhos_detalhe'),
    path('empenhos/<int:pk>/liberar/', views.EmpenhoLiberar.as_view(), name='empenhos_liberar'),
]
