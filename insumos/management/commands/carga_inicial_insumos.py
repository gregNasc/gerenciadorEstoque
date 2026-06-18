from django.core.management.base import BaseCommand
from insumos.models import CategoriaInsumo, Insumo

class Command(BaseCommand):

    help = 'Carga inicial de categorias e insumos'

    DADOS = {
        'DEPARTAMENTO PESSOAL': [
            {
                'descricao': 'Toner Impressora Laser',
                'unidade': 'UN',
                'tipo': 'QUANTIDADE',
            },
            {
                'descricao': 'Marcador de Coleta - AZUL ESCURO',
                'unidade': 'UN',
                'tipo': 'QUANTIDADE',
            },
            {
                'descricao': 'Marcador de Coleta - AZUL CLARO',
                'unidade': 'UN',
                'tipo': 'QUANTIDADE',
            },
            {
                'descricao': 'Marcador de Coleta - LARANJA',
                'unidade': 'UN',
                'tipo': 'QUANTIDADE',
            },
            {
                'descricao': 'Touca',
                'unidade': 'UN',
                'tipo': 'QUANTIDADE',
            },
            {
                'descricao': 'Luva',
                'unidade': 'PAR',
                'tipo': 'QUANTIDADE',
            },
            {
                'descricao': 'Máscara',
                'unidade': 'UN',
                'tipo': 'QUANTIDADE',
            },
            {
                'descricao': 'Grampeador',
                'unidade': 'UN',
                'tipo': 'REUTILIZAVEL',
            },
            {
                'descricao': 'Durex',
                'unidade': 'UN',
                'tipo': 'QUANTIDADE',
            },
            {
                'descricao': 'Papel Sulfite (Pacote)',
                'unidade': 'PCT',
                'tipo': 'QUANTIDADE',
            },
            {
                'descricao': 'Etiqueta Setor 0001',
                'unidade': 'ROLO',
                'tipo': 'LOTE',
            },
            {
                'descricao': 'Etiqueta Setor 1000',
                'unidade': 'ROLO',
                'tipo': 'LOTE',
            },
            {
                'descricao': 'Etiqueta Setor 2000',
                'unidade': 'ROLO',
                'tipo': 'LOTE',
            },
            {
                'descricao': 'Etiqueta Setor 3000',
                'unidade': 'ROLO',
                'tipo': 'LOTE',
            },
            {
                'descricao': 'Etiqueta Setor 3500 - Peso Variável',
                'unidade': 'ROLO',
                'tipo': 'LOTE',
            },
            {
                'descricao': 'Etiqueta Setor 4000',
                'unidade': 'ROLO',
                'tipo': 'LOTE',
            },
            {
                'descricao': 'Etiqueta Setor 5000',
                'unidade': 'ROLO',
                'tipo': 'LOTE',
            },
            {
                'descricao': 'Etiqueta Setor 6000',
                'unidade': 'ROLO',
                'tipo': 'LOTE',
            },
            {
                'descricao': 'Etiqueta Setor 7000',
                'unidade': 'ROLO',
                'tipo': 'LOTE',
            },
            {
                'descricao': 'Etiqueta Setor 8000',
                'unidade': 'ROLO',
                'tipo': 'LOTE',
            },
            {
                'descricao': 'Etiqueta Setor 9000',
                'unidade': 'ROLO',
                'tipo': 'LOTE',
            },
            {
                'descricao': 'Etiqueta Setor 10000',
                'unidade': 'ROLO',
                'tipo': 'LOTE',
            },
            {
                'descricao': 'Etiqueta Setor 11000',
                'unidade': 'ROLO',
                'tipo': 'LOTE',
            },
            {
                'descricao': 'Etiqueta Setor 12000',
                'unidade': 'ROLO',
                'tipo': 'LOTE',
            },
            {
                'descricao': 'Etiqueta Setor 13000',
                'unidade': 'ROLO',
                'tipo': 'LOTE',
            },
            {
                'descricao': 'Etiqueta Setor 14000',
                'unidade': 'ROLO',
                'tipo': 'LOTE',
            },
            {
                'descricao': 'Etiqueta Setor 15000',
                'unidade': 'ROLO',
                'tipo': 'LOTE',
            },
            {
                'descricao': 'Etiqueta Setor 16000',
                'unidade': 'ROLO',
                'tipo': 'LOTE',
            },
            {
                'descricao': 'Etiqueta Setor 17000',
                'unidade': 'ROLO',
                'tipo': 'LOTE',
            },
            {
                'descricao': 'Etiqueta Setor 18000',
                'unidade': 'ROLO',
                'tipo': 'LOTE',
            },
            {
                'descricao': 'Etiqueta Setor 19000',
                'unidade': 'ROLO',
                'tipo': 'LOTE',
            },
            {
                'descricao': 'Etiqueta Setor 20000',
                'unidade': 'ROLO',
                'tipo': 'LOTE',
            },
            {
                'descricao': 'Marcador Coletado',
                'unidade': 'UN',
                'tipo': 'QUANTIDADE',
            },
        ],

        'EPI': [
            {
                'descricao': 'Calça Térmica',
                'unidade': 'UN',
                'tipo': 'REUTILIZAVEL',
            },
            {
                'descricao': 'Capa Térmica',
                'unidade': 'UN',
                'tipo': 'REUTILIZAVEL',
            },
            {
                'descricao': 'Capacete',
                'unidade': 'UN',
                'tipo': 'REUTILIZAVEL',
            },
            {
                'descricao': 'Botas do 33/48',
                'unidade': 'PAR',
                'tipo': 'REUTILIZAVEL',
            },
            {
                'descricao': 'Cinto de Segurança',
                'unidade': 'UN',
                'tipo': 'REUTILIZAVEL',
            },
        ],

        'FIOS E CABOS': [
            {
                'descricao': 'Cabo Power',
                'unidade': 'UN',
                'tipo': 'REUTILIZAVEL',
            },
            {
                'descricao': 'Cabo USB (Impressora)',
                'unidade': 'UN',
                'tipo': 'REUTILIZAVEL',
            },
            {
                'descricao': 'Filtro de Linha',
                'unidade': 'UN',
                'tipo': 'REUTILIZAVEL',
            },
            {
                'descricao': 'Transformador',
                'unidade': 'UN',
                'tipo': 'REUTILIZAVEL',
            },
            {
                'descricao': 'Cabo Transformador',
                'unidade': 'UN',
                'tipo': 'REUTILIZAVEL',
            },
            {
                'descricao': 'Adaptador',
                'unidade': 'UN',
                'tipo': 'REUTILIZAVEL',
            },
            {
                'descricao': 'Extensão',
                'unidade': 'UN',
                'tipo': 'REUTILIZAVEL',
            },
            {
                'descricao': 'Cabo de Rede (RJ45)',
                'unidade': 'UN',
                'tipo': 'REUTILIZAVEL',
            },
            {
                'descricao': 'Extensor de Rede / Carrinho',
                'unidade': 'UN',
                'tipo': 'REUTILIZAVEL',
            },
            {
                'descricao': 'Cintos Coletor',
                'unidade': 'UN',
                'tipo': 'REUTILIZAVEL',
            },
        ],

        'ACESSORIOS COLETOR': [
            {
                'descricao': 'Carregador de Bateria',
                'unidade': 'UN',
                'tipo': 'REUTILIZAVEL',
            },
            {
                'descricao': 'Fonte Carregador de Bateria',
                'unidade': 'UN',
                'tipo': 'REUTILIZAVEL',
            },
            {
                'descricao': 'Bateria Coletor',
                'unidade': 'UN',
                'tipo': 'REUTILIZAVEL',
            },
            {
                'descricao': 'Carregador Tipo C (Coletor Android)',
                'unidade': 'UN',
                'tipo': 'REUTILIZAVEL',
            },
            {
                'descricao': 'Berço + Cabo USB',
                'unidade': 'UN',
                'tipo': 'REUTILIZAVEL',
            },
            {
                'descricao': 'Mouse',
                'unidade': 'UN',
                'tipo': 'REUTILIZAVEL',
            },
            {
                'descricao': 'Placa 3G',
                'unidade': 'UN',
                'tipo': 'REUTILIZAVEL',
            },
            {
                'descricao': 'Fonte Notebook',
                'unidade': 'UN',
                'tipo': 'REUTILIZAVEL',
            },
            {
                'descricao': 'Fonte Balança',
                'unidade': 'UN',
                'tipo': 'REUTILIZAVEL',
            },
        ],

        'OPERACIONAL': [
            {
                'descricao': 'Escada',
                'unidade': 'UN',
                'tipo': 'REUTILIZAVEL',
            },
            {
                'descricao': 'Balança',
                'unidade': 'UN',
                'tipo': 'REUTILIZAVEL',
            },
        ],
    }

    def handle(self, *args, **options):

        total_categorias = 0
        total_insumos = 0

        for categoria_nome, itens in self.DADOS.items():

            categoria, created = CategoriaInsumo.objects.get_or_create(
                nome=categoria_nome
            )

            if created:
                total_categorias += 1

            for item in itens:

                _, created = Insumo.objects.get_or_create(
                    descricao=item['descricao'],
                    categoria=categoria,
                    defaults={
                        'unidade_medida': item['unidade'],
                        'tipo_controle': item['tipo'],
                        'ativo': True,
                    }
                )

                if created:
                    total_insumos += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Carga concluída. '
                f'Categorias criadas: {total_categorias} | '
                f'Insumos criados: {total_insumos}'
            )
        )