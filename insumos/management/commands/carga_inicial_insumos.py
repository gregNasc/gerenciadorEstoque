from django.core.management.base import BaseCommand
from insumos.models import CategoriaInsumo, Insumo


TAG_DESCRICOES = (
    'Etiqueta Setor 00001',
    'Etiqueta Setor 01000',
    'Etiqueta Setor 02000',
    'Etiqueta Setor 03000',
    'Etiqueta Setor 03500 - Peso Variável',
    'Etiqueta Setor 04000',
    'Etiqueta Setor 05000',
    'Etiqueta Setor 06000',
    'Etiqueta Setor 07000',
    'Etiqueta Setor 08000',
    'Etiqueta Setor 09000',
    'Etiqueta Setor 10000',
    'Etiqueta Setor 11000',
    'Etiqueta Setor 12000',
    'Etiqueta Setor 13000',
    'Etiqueta Setor 14000',
    'Etiqueta Setor 15000',
    'Etiqueta Setor 16000',
    'Etiqueta Setor 17000',
    'Etiqueta Setor 18000',
    'Etiqueta Setor 19000',
    'Etiqueta Setor 20000',
)

TAG_INSUMOS = [
    {
        'descricao': descricao,
        'unidade': 'ROLO',
        'tipo': 'LOTE',
    }
    for descricao in TAG_DESCRICOES
]


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
                'unidade': 'UN',
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
                'descricao': 'Marcador Coletado',
                'unidade': 'UN',
                'tipo': 'QUANTIDADE',
            },
        ],

        'TAGS': TAG_INSUMOS,

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

            categoria = CategoriaInsumo.objects.filter(nome__iexact=categoria_nome).first()
            created = categoria is None
            if created:
                categoria = CategoriaInsumo.objects.create(nome=categoria_nome)

            if created:
                total_categorias += 1

            for item in itens:

                insumo = Insumo.objects.filter(
                    descricao__iexact=item['descricao'], categoria=categoria,
                ).first()
                created = insumo is None
                if created:
                    insumo = Insumo.objects.create(
                        descricao=item['descricao'], categoria=categoria,
                        unidade_medida=item['unidade'],
                        tipo_controle=item['tipo'],
                        ativo=True,
                    )
                else:
                    campos = []
                    if insumo.unidade_medida != item['unidade']:
                        insumo.unidade_medida = item['unidade']
                        campos.append('unidade_medida')
                    if insumo.tipo_controle != item['tipo']:
                        insumo.tipo_controle = item['tipo']
                        campos.append('tipo_controle')
                    if not insumo.ativo:
                        insumo.ativo = True
                        campos.append('ativo')
                    if campos:
                        insumo.save(update_fields=campos)

                if created:
                    total_insumos += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Carga concluída. '
                f'Categorias criadas: {total_categorias} | '
                f'Insumos criados: {total_insumos}'
            )
        )
