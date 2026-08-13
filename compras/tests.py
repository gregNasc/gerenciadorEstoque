import uuid
from decimal import Decimal
from io import BytesIO

from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from openpyxl import Workbook

from compras.models import (
    Aquisicao,
    HistoricoValorEquipamento,
    ItemAquisicao,
    RemessaCompra,
)
from compras.services import AquisicaoService, RemessaCompraService
from estoque.models import Base, Comunicado, Empresa, Equipamento, Perfil, Produto
from estoque.policies.compras import GruposCorporativos
from estoque.services.sick_service import SickService
from insumos.models import CategoriaInsumo, FornecedorInsumo, Insumo, SaldoInsumoBase
from insumos.services.movimentacao_service import MovimentacaoService
from ordens_servico.models import OrdemServico


@override_settings(
    PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
)
class ComprasRemessasTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nome='Empresa Compras')
        self.matriz = Base.objects.create(nome='Matriz', empresa=self.empresa)
        self.base = Base.objects.create(nome='Base destino', empresa=self.empresa)
        self.admin = self._usuario('admin_compras', Perfil.Role.ADMIN)
        self.outro_admin = self._usuario('admin_acompanhamento', Perfil.Role.ADMIN)
        self.gestor = self._usuario('gestor_destino', Perfil.Role.GESTOR, self.base)
        self.fornecedor = FornecedorInsumo.objects.create(
            nome='Fornecedor Compras', documento='12345678000190'
        )
        categoria = CategoriaInsumo.objects.create(nome='Categoria Compras')
        self.insumo = Insumo.objects.create(
            descricao='Insumo Compras', categoria=categoria, unidade_medida='UN'
        )
        self.produto = Produto.objects.create(
            codigo='PROD-COMPRA', descricao='Equipamento compra', fabricante='Marca',
            modelo='Modelo', categoria='Coletores',
        )

    @staticmethod
    def _usuario(username, role, base=None):
        user = User.objects.create_user(username, password='senha-forte')
        user.perfil.role = role
        user.perfil.empresa = None if role == Perfil.Role.ADMIN else base.empresa
        user.perfil.save()
        if base:
            user.perfil.regionais.add(base)
        return user

    def _aquisicao(self, quantidade=100):
        aquisicao = AquisicaoService.criar(
            empresa=self.empresa, fornecedor=self.fornecedor, usuario=self.admin,
            numero_documento='NF-123',
            itens=[{
                'tipo_item': ItemAquisicao.Tipo.INSUMO,
                'insumo': self.insumo,
                'quantidade': quantidade,
                'valor_unitario': Decimal('7.50'),
            }],
        )
        AquisicaoService.aprovar(aquisicao, self.admin)
        return aquisicao

    def test_fornecedor_direto_recebe_parcial_e_idempotente(self):
        aquisicao = self._aquisicao()
        with self.captureOnCommitCallbacks(execute=True):
            remessa = RemessaCompraService.criar(
                empresa=self.empresa, fluxo=RemessaCompra.Fluxo.FORNECEDOR_DIRETO,
                aquisicao=aquisicao, base_destino=self.base, usuario=self.admin,
                itens=[{
                    'item_aquisicao': aquisicao.itens.get(),
                    'insumo': self.insumo,
                    'quantidade_prevista': 100,
                    'custo_unitario_snapshot': Decimal('7.50'),
                }],
            )
            RemessaCompraService.enviar(remessa, self.admin)
        chave = uuid.uuid4()
        dados = [{
            'item_id': remessa.itens.get().pk,
            'quantidade_recebida': 98,
            'quantidade_faltante': 2,
        }]
        with self.captureOnCommitCallbacks(execute=True):
            primeiro = RemessaCompraService.confirmar(
                remessa=remessa, usuario=self.gestor, idempotency_key=chave,
                linhas=dados, finalizar=True,
            )
            segundo = RemessaCompraService.confirmar(
                remessa=remessa, usuario=self.gestor, idempotency_key=chave,
                linhas=dados, finalizar=True,
            )
        self.assertEqual(primeiro.pk, segundo.pk)
        remessa.refresh_from_db()
        saldo = SaldoInsumoBase.objects.get(base=self.base, insumo=self.insumo)
        self.assertEqual(saldo.saldo, Decimal('98'))
        self.assertEqual(saldo.custo_medio, Decimal('7.50'))
        self.assertEqual(remessa.status, RemessaCompra.Status.RECEBIDA_PARCIAL)
        self.assertTrue(OrdemServico.objects.filter(chamado_referencia=remessa.protocolo).exists())
        comunicado = Comunicado.objects.filter(dados__remessa_id=remessa.pk).latest('pk')
        self.assertTrue(comunicado.usuarios.filter(pk=self.admin.pk).exists())
        self.assertTrue(comunicado.usuarios.filter(pk=self.outro_admin.pk).exists())
        self.assertTrue(comunicado.usuarios.filter(pk=self.gestor.pk).exists())

    def test_entre_bases_reserva_impede_consumo_e_libera_faltante(self):
        MovimentacaoService.entrada(
            base=self.matriz, insumo=self.insumo, quantidade=100,
            valor_unitario=5, usuario=self.admin,
        )
        remessa = RemessaCompraService.criar(
            empresa=self.empresa, fluxo=RemessaCompra.Fluxo.ENTRE_BASES,
            base_origem=self.matriz, base_destino=self.base, usuario=self.admin,
            itens=[{'insumo': self.insumo, 'quantidade_prevista': 40, 'custo_unitario_snapshot': 5}],
        )
        saldo = SaldoInsumoBase.objects.get(base=self.matriz, insumo=self.insumo)
        self.assertEqual(saldo.saldo_reservado, Decimal('40'))
        with self.assertRaises(ValueError):
            MovimentacaoService.saida(
                base=self.matriz, insumo=self.insumo, quantidade=70, usuario=self.admin,
            )
        RemessaCompraService.enviar(remessa, self.admin)
        RemessaCompraService.confirmar(
            remessa=remessa, usuario=self.gestor, idempotency_key=uuid.uuid4(),
            linhas=[{
                'item_id': remessa.itens.get().pk,
                'quantidade_recebida': 30,
                'quantidade_faltante': 10,
            }],
            finalizar=True,
        )
        origem = SaldoInsumoBase.objects.get(base=self.matriz, insumo=self.insumo)
        destino = SaldoInsumoBase.objects.get(base=self.base, insumo=self.insumo)
        self.assertEqual((origem.saldo, origem.saldo_reservado), (Decimal('70'), Decimal('0')))
        self.assertEqual(destino.saldo, Decimal('30'))

    def test_valor_equipamento_mantem_historico(self):
        equipamento = Equipamento.objects.create(
            produto=self.produto, numero_serie='SERIE-COMPRA', patrimonio='PAT-COMPRA',
            regional=self.base, codigo='EQP-COMPRA',
        )
        AquisicaoService.atualizar_valor_equipamento(
            equipamento=equipamento, usuario=self.admin,
            custo=1000, referencia=1200,
            origem=Equipamento.OrigemValor.INFORMADO_COMPRAS,
            motivo='Valor confirmado na nota', fornecedor=self.fornecedor,
        )
        AquisicaoService.atualizar_valor_equipamento(
            equipamento=equipamento, usuario=self.admin,
            custo=950, referencia=1200,
            origem=Equipamento.OrigemValor.DOCUMENTO_COMPRA,
            motivo='Desconto identificado', fornecedor=self.fornecedor,
        )
        self.assertEqual(HistoricoValorEquipamento.objects.filter(equipamento=equipamento).count(), 2)
        equipamento.refresh_from_db()
        self.assertEqual(equipamento.custo_aquisicao, Decimal('950'))

    def test_importacao_precificacao_ignora_cabecalho_e_atualiza_equipamento(self):
        equipamento = Equipamento.objects.create(
            produto=self.produto, numero_serie='SERIE-IMPORTACAO', patrimonio='PAT-IMPORTACAO',
            regional=self.base, codigo='EQP-IMPORTACAO',
        )
        workbook = Workbook()
        planilha = workbook.active
        planilha.title = 'PRECIFICACAO'
        planilha.append([
            'EQUIPAMENTO_ID', 'REGIONAL', 'CATEGORIA', 'EQUIPAMENTO', 'PATRIMONIO',
            'NUMERO_SERIE', 'CUSTO_AQUISICAO', 'PRECO_REFERENCIA', 'ORIGEM_VALOR', 'MOTIVO',
        ])
        planilha.append([
            equipamento.pk, self.base.nome, self.produto.categoria, self.produto.descricao,
            equipamento.patrimonio, equipamento.numero_serie, 800, 900,
            Equipamento.OrigemValor.INFORMADO_COMPRAS, 'IMPORTAÇÃO DO TEMPLATE',
        ])
        conteudo = BytesIO()
        workbook.save(conteudo)
        arquivo = SimpleUploadedFile(
            'template-precificacao-equipamentos.xlsx', conteudo.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

        self.client.force_login(self.admin)
        resposta = self.client.post(
            reverse('compras:importar_precificacao_equipamentos'),
            {'arquivo': arquivo},
        )

        self.assertRedirects(resposta, reverse('compras:valores_equipamentos'))
        equipamento.refresh_from_db()
        self.assertEqual(equipamento.custo_aquisicao, Decimal('800'))
        self.assertEqual(equipamento.preco_referencia, Decimal('900'))
        self.assertEqual(
            HistoricoValorEquipamento.objects.filter(equipamento=equipamento).count(),
            1,
        )

    def test_paginas_financeiras_e_badge_para_admins_e_envolvidos(self):
        self._aquisicao(1)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('compras:aquisicao_lista')).status_code, 200)
        self.assertEqual(self.client.get(reverse('compras:valores_insumos')).status_code, 200)
        self.assertEqual(self.client.get(reverse('compras:valores_equipamentos')).status_code, 200)

    def test_painel_de_valores_pagina_e_pesquisa_o_inventario_detalhado(self):
        Equipamento.objects.bulk_create([
            Equipamento(
                produto=self.produto, numero_serie=f'SERIE-PAINEL-{indice:02d}',
                patrimonio=f'PAT-PAINEL-{indice:02d}', regional=self.base,
                codigo=f'EQP-PAINEL-{indice:02d}', preco_referencia=indice * 100,
                origem_valor=Equipamento.OrigemValor.ESTIMATIVA_MERCADO,
            )
            for indice in range(1, 22)
        ])
        self.client.force_login(self.admin)

        resposta = self.client.get(reverse('compras:valores_equipamentos'))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context['total_equipamentos'], 21)
        self.assertEqual(len(resposta.context['equipamentos']), 20)
        self.assertEqual(resposta.context['page_obj'].paginator.num_pages, 2)
        self.assertContains(resposta, 'Consultar inventario detalhado')

        resposta_busca = self.client.get(
            reverse('compras:valores_equipamentos'),
            {'q': 'PAT-PAINEL-21'},
        )
        self.assertEqual(resposta_busca.context['total_equipamentos'], 1)
        self.assertContains(resposta_busca, 'PAT-PAINEL-21')
        self.assertNotContains(resposta_busca, 'PAT-PAINEL-20')

    def test_admin_atende_solicitacoes_mas_nao_cria(self):
        self.client.force_login(self.admin)
        self.assertEqual(
            self.client.get(reverse('insumos:criar_solicitacao_insumo')).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(reverse('estoque:criar_solicitacao')).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(reverse('insumos:lista_solicitacoes_insumo')).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse('estoque:caixa_solicitacoes')).status_code,
            200,
        )


class ManutencaoMatrizExclusivaTests(TestCase):
    def setUp(self):
        empresa = Empresa.objects.create(nome='Empresa Matriz')
        self.base = Base.objects.create(nome='Base Matriz', empresa=empresa)
        produto = Produto.objects.create(
            codigo='PROD-MATRIZ', descricao='Coletor Matriz', fabricante='Marca',
            modelo='Modelo', categoria='Coletores',
        )
        self.equipamento = Equipamento.objects.create(
            produto=produto, numero_serie='SERIE-MATRIZ', patrimonio='PAT-MATRIZ',
            regional=self.base, codigo='EQP-MATRIZ',
        )
        self.gestor = User.objects.create_user('gestor_matriz')
        self.gestor.perfil.role = Perfil.Role.GESTOR
        self.gestor.perfil.empresa = empresa
        self.gestor.perfil.save()
        self.gestor.perfil.regionais.add(self.base)
        self.admin_comum = User.objects.create_user('admin_sem_manutencao')
        self.admin_comum.perfil.role = Perfil.Role.ADMIN
        self.admin_comum.perfil.save()
        self.rafael = User.objects.create_user('rafael.ribeiro')
        self.rafael.perfil.role = Perfil.Role.OPERADOR
        self.rafael.perfil.save()
        grupo, _ = Group.objects.get_or_create(name=GruposCorporativos.SICK_MANUTENCAO)
        self.rafael.groups.add(grupo)

    def test_admin_comum_nao_executa_e_tecnico_autorizado_executa(self):
        sick = SickService.marcar_como_sick(
            equipamento_id=self.equipamento.pk, usuario=self.gestor,
            categoria='Hardware', motivo='Falha', observacao='Falha',
        )
        SickService.enviar_para_manutencao(
            sick_id=sick.pk, usuario=self.gestor, destino='Matriz',
        )
        with self.assertRaises(PermissionDenied):
            SickService.confirmar_recebimento(sick_id=sick.pk, usuario=self.admin_comum)
        SickService.confirmar_recebimento(sick_id=sick.pk, usuario=self.rafael)
        sick.refresh_from_db()
        self.assertEqual(sick.etapa, 'RECEBIDO')
