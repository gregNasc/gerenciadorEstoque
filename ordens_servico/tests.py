from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from estoque.models import Base, Empresa, Equipamento, Perfil, Produto
from estoque.services.sick_service import SickService
from estoque.services.transferencia_services import criar_transferencia
from insumos.models import CategoriaInsumo, Insumo
from insumos.services.movimentacao_service import MovimentacaoService
from insumos.services.solicitacao_service import SolicitacaoService
from ordens_servico.models import OrdemServico, OrdemServicoAssinatura
from ordens_servico.services import OrdemServicoService


class OrdemServicoFluxosTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nome='Empresa O.S.')
        self.origem = Base.objects.create(nome='Origem', empresa=self.empresa)
        self.destino = Base.objects.create(nome='Destino', empresa=self.empresa)
        self.admin = User.objects.create_user('admin_os', password='Senha-forte-123')
        self.admin.perfil.role = Perfil.Role.ADMIN
        self.admin.perfil.save(update_fields=['role', 'empresa'])
        self.produto = Produto.objects.create(
            codigo='PROD-OS', descricao='Notebook O.S.', fabricante='Fabricante',
            modelo='Modelo', categoria='Notebooks',
        )
        self.equipamento = Equipamento.objects.create(
            produto=self.produto, numero_serie='SERIE-OS-1', patrimonio='PAT-OS-1',
            regional=self.origem, codigo='EQP-OS-1',
        )
        categoria = CategoriaInsumo.objects.create(nome='Categoria O.S.')
        self.insumo = Insumo.objects.create(
            descricao='Papel O.S.', categoria=categoria, unidade_medida='UN',
        )

    def test_transferencia_emite_os_idempotente_com_snapshot(self):
        transferencia = criar_transferencia(
            equipamentos=[self.equipamento], regional_destino=self.destino,
            solicitado_por=self.admin,
        )
        ordem = OrdemServico.objects.get(transferencia=transferencia)
        self.assertEqual(ordem.tipo, OrdemServico.Tipo.TRANSFERENCIA)
        self.assertEqual(ordem.linhas.get().numero_serie, 'SERIE-OS-1')
        self.assertEqual(
            OrdemServicoService.para_transferencia(transferencia, self.admin).pk,
            ordem.pk,
        )

    def test_sick_e_movimentacao_de_insumo_emitem_os(self):
        sick = SickService.marcar_como_sick(
            equipamento_id=self.equipamento.pk, usuario=self.admin,
            categoria='Hardware', motivo='Falha', observacao='Não inicializa.',
        )
        self.assertTrue(OrdemServico.objects.filter(sick=sick).exists())
        movimento = MovimentacaoService.entrada(
            base=self.origem, insumo=self.insumo, quantidade=10,
            valor_unitario=Decimal('4.50'), usuario=self.admin,
        )
        ordem = OrdemServico.objects.get(movimentacao_insumo=movimento)
        self.assertEqual(ordem.linhas.get().quantidade, Decimal('10'))

    def test_encaminhamento_de_insumos_emite_e_finaliza_os(self):
        solicitacao = SolicitacaoService.criar_solicitacao(
            base=self.destino, solicitante=self.admin, justificativa='Reposição',
            prioridade='MEDIA', itens=[{'insumo': self.insumo, 'quantidade': 3}],
        )
        SolicitacaoService.aprovar(solicitacao=solicitacao, usuario=self.admin)
        SolicitacaoService.colocar_em_compra(solicitacao=solicitacao, usuario=self.admin)
        ordem = OrdemServico.objects.get(solicitacao_insumo=solicitacao)
        self.assertEqual(ordem.status, OrdemServico.Status.EM_EXECUCAO)
        SolicitacaoService.finalizar(solicitacao=solicitacao, usuario=self.admin)
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, OrdemServico.Status.CONCLUIDA)

    def test_assinatura_valida_senha_e_nao_armazena_segredo(self):
        movimento = MovimentacaoService.entrada(
            base=self.origem, insumo=self.insumo, quantidade=1,
            valor_unitario=1, usuario=self.admin,
        )
        ordem = OrdemServico.objects.get(movimentacao_insumo=movimento)
        with self.assertRaises(ValidationError):
            OrdemServicoService.assinar(
                ordem=ordem, usuario=self.admin, senha='incorreta',
                tipo=OrdemServicoAssinatura.Tipo.ENCERRAMENTO,
            )
        self.assertFalse(ordem.assinaturas.exists())
        assinatura = OrdemServicoService.assinar(
            ordem=ordem, usuario=self.admin, senha='Senha-forte-123',
            tipo=OrdemServicoAssinatura.Tipo.ENCERRAMENTO,
        )
        self.assertEqual(len(assinatura.hash_documento), 64)
        self.assertFalse(any(field.name == 'senha' for field in assinatura._meta.fields))
        with self.assertRaises(ValidationError):
            OrdemServicoService.assinar(
                ordem=ordem, usuario=self.admin, senha='Senha-forte-123',
                tipo=OrdemServicoAssinatura.Tipo.ENCERRAMENTO,
            )

    def test_visualizacao_impressao_pdf_e_saude_estoque(self):
        movimento = MovimentacaoService.entrada(
            base=self.origem, insumo=self.insumo, quantidade=2,
            valor_unitario=1, usuario=self.admin,
        )
        ordem = OrdemServico.objects.get(movimentacao_insumo=movimento)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('ordens_servico:detalhe', args=[ordem.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('ordens_servico:imprimir', args=[ordem.pk])).status_code, 200)
        resposta_pdf = self.client.get(reverse('ordens_servico:pdf', args=[ordem.pk]))
        self.assertEqual(resposta_pdf.status_code, 200)
        self.assertEqual(resposta_pdf['Content-Type'], 'application/pdf')
        self.assertContains(
            self.client.get(reverse('insumos:dashboard_saude_equipamentos')),
            'Equipamentos', status_code=200,
        )
        self.assertContains(
            self.client.get(reverse('insumos:dashboard_saude_geral')),
            'Visão geral', status_code=200,
        )
