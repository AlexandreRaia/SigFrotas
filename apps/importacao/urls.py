from django.urls import path

from . import motoristas, veiculos, views

urlpatterns = [
    path('', views.Inicio.as_view(), name='importacao_inicio'),
    path('veiculos/', views.Importar.as_view(
        importador=veiculos, titulo='Importar veículos', permissoes=('frota.gerir',), voltar='veiculos_lista',
        modelo_url='importacao_modelo_veiculos'), name='importacao_veiculos'),
    path('veiculos/modelo.csv', views.Modelo.as_view(importador=veiculos, nome='modelo_veiculos.csv'),
         name='importacao_modelo_veiculos'),
    path('motoristas/', views.Importar.as_view(
        importador=motoristas, titulo='Importar motoristas', permissoes=('pessoas.gerir', 'pessoas.dados_pessoais'),
        voltar='motoristas_lista', modelo_url='importacao_modelo_motoristas'), name='importacao_motoristas'),
    path('motoristas/modelo.csv', views.Modelo.as_view(importador=motoristas, nome='modelo_motoristas.csv'),
         name='importacao_modelo_motoristas'),
]
