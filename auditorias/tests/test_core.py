from datetime import timedelta
import json
import uuid

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from estoque.models import Base, Empresa, Equipamento, GrupoRegional, Produto
from estoque.services.transferencia_services import enviar_transferencia, receber_transferencia

from auditorias.models import AuditoriaBase, AuditoriaDivergencia, CampanhaAuditoria
from auditorias.services.encerramento_service import EncerramentoService
from auditorias.services.apuracao_service import ApuracaoService
from auditorias.services.campanha_service import CampanhaService
from auditorias.services.leitura_service import LeituraService
from auditorias.services.regularizacao_service import RegularizacaoService
from auditorias.services.relatorio_service import RelatorioService
from auditorias.services.snapshot_service import SnapshotService


class AuditoriaFixtureMixin:
    def setUp(self):
        self.empresa = Empresa.objects.create(nome='Empresa A')
        self.grupo = GrupoRegional.objects.create(nome='Interior')
        self.base = Base.objects.create(empresa=self.empresa, nome='Base A', grupo_regional=self.grupo)
        self.outra_base = Base.objects.create(empresa=self.empresa, nome='Base B', grupo_regional=self.grupo)
        self.destino = Base.objects.create(empresa=self.empresa, nome='Base C', grupo_regional=self.grupo)
        self.user = User.objects.create_user('gestor', password='teste')
        self.user.perfil.role = 'gestor'
        self.user.perfil.empresa = self.empresa
        self.user.perfil.save()
        self.user.perfil.regionais.add(self.base)
        self.admin = User.objects.create_superuser('admin-auditoria', password='teste')
        self.produto = Produto.objects.create(
            codigo='P1', descricao='Coletor', fabricante='Zebra', modelo='TC', categoria='Coletores'
        )
        self.campanha = CampanhaAuditoria.objects.create(
            empresa=self.empresa,
            nome='Inventário anual',
            criado_por=self.user,
            status=CampanhaAuditoria.Status.AGENDADA,
        )
        self.auditoria = AuditoriaBase.objects.create(
            campanha=self.campanha,
            base=self.base,
            inicio_em=timezone.now() - timedelta(hours=1),
            fim_em=timezone.now() + timedelta(days=1),
            status=AuditoriaBase.Status.DISPONIVEL,
        )

    def equipamento(self, *, base=None, sufixo='1'):
        return Equipamento.objects.create(
            produto=self.produto,
            numero_serie=f'SERIE{sufixo}',
            patrimonio=f'PAT{sufixo}',
            codigo=f'EQP-{sufixo}',
            regional=base or self.base,
        )


class AuditoriaModelTests(AuditoriaFixtureMixin, TestCase):
    def test_periodo_invertido_e_acima_de_31_dias_sao_rejeitados(self):
        agora = timezone.now()
        invertida = AuditoriaBase(
            campanha=self.campanha, base=self.outra_base,
            inicio_em=agora, fim_em=agora - timedelta(seconds=1),
        )
        with self.assertRaises(ValidationError):
            invertida.full_clean()
        longa = AuditoriaBase(
            campanha=self.campanha, base=self.outra_base,
            inicio_em=agora, fim_em=agora + timedelta(days=31, seconds=1),
        )
        with self.assertRaises(ValidationError):
            longa.full_clean()

    def test_base_de_outra_empresa_e_rejeitada(self):
        outra_empresa = Empresa.objects.create(nome='Empresa B')
        base_externa = Base.objects.create(empresa=outra_empresa, nome='Externa')
        self.auditoria.base = base_externa
        with self.assertRaises(ValidationError):
            self.auditoria.full_clean()


class FluxoAuditoriaTests(AuditoriaFixtureMixin, TestCase):
    def test_tela_de_coleta_renderiza_com_csrf(self):
        self.client.force_login(self.user)
        resposta = self.client.get(f'/auditorias/bases/{self.auditoria.pk}/coleta/')
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'name="csrfmiddlewaretoken"')

    def test_snapshot_e_imutavel_e_preserva_dados(self):
        equipamento = self.equipamento()
        SnapshotService.criar_snapshot(self.auditoria, self.user)
        snapshot = self.auditoria.snapshot_equipamentos.get()
        equipamento.regional = self.outra_base
        equipamento.status = 'SICK'
        equipamento.save()
        snapshot.refresh_from_db()
        self.assertEqual(snapshot.base_esperada, self.base)
        self.assertEqual(snapshot.status, 'ATIVO')
        with self.assertRaises(ValidationError):
            snapshot.save()

    def test_leitura_outra_base_e_idempotente(self):
        equipamento = self.equipamento(base=self.outra_base)
        SnapshotService.criar_snapshot(self.auditoria, self.user)
        chave = uuid.uuid4()
        resultado = LeituraService.registrar(
            auditoria_base=self.auditoria,
            valor=equipamento.patrimonio.lower(),
            usuario=self.user,
            idempotency_key=chave,
        )
        repetida = LeituraService.registrar(
            auditoria_base=self.auditoria,
            valor=equipamento.patrimonio,
            usuario=self.user,
            idempotency_key=chave,
        )
        self.assertEqual(resultado.leitura.pk, repetida.leitura.pk)
        self.assertEqual(resultado.leitura.classificacao, 'OUTRA_BASE')
        self.assertEqual(self.auditoria.divergencias.get().tipo, AuditoriaDivergencia.Tipo.OUTRA_BASE)

    def test_encerramento_gera_nao_localizado_uma_unica_vez(self):
        self.equipamento()
        SnapshotService.criar_snapshot(self.auditoria, self.user)
        EncerramentoService.enviar(self.auditoria, self.user)
        self.auditoria.refresh_from_db()
        self.assertEqual(self.auditoria.status, AuditoriaBase.Status.ENVIADA)
        self.assertEqual(
            self.auditoria.divergencias.filter(tipo=AuditoriaDivergencia.Tipo.NAO_LOCALIZADO).count(),
            1,
        )

    def test_reabrir_antes_da_validacao_preserva_leituras(self):
        equipamento = self.equipamento()
        SnapshotService.criar_snapshot(self.auditoria, self.user)
        EncerramentoService.enviar(self.auditoria, self.user)
        CampanhaService.reabrir_base(self.auditoria, self.admin, 'Continuar a coleta interrompida.')
        leitura = LeituraService.registrar(
            auditoria_base=self.auditoria,
            valor=equipamento.patrimonio,
            usuario=self.user,
        ).leitura
        self.assertEqual(leitura.classificacao, 'CORRETO')
        self.assertEqual(
            self.auditoria.divergencias.get(tipo=AuditoriaDivergencia.Tipo.NAO_LOCALIZADO).status,
            AuditoriaDivergencia.Status.CANCELADA,
        )

    def test_manter_na_base_altera_equipamento_sem_alterar_snapshot(self):
        esperado = self.equipamento(base=self.outra_base)
        SnapshotService.criar_snapshot(self.auditoria, self.user)
        leitura = LeituraService.registrar(
            auditoria_base=self.auditoria,
            valor=esperado.numero_serie,
            usuario=self.user,
        ).leitura
        divergencia = leitura.divergencias.get()
        EncerramentoService.enviar(self.auditoria, self.user)
        ApuracaoService.solicitar_correcao(
            self.auditoria,
            self.admin,
            prazo_correcao_em=timezone.now() + timedelta(days=2),
            orientacoes='Regularizar a base encontrada.',
        )
        RegularizacaoService.manter_na_base(
            divergencia=divergencia,
            usuario=self.user,
            justificativa='Equipamento incorporado à base.',
        )
        esperado.refresh_from_db()
        divergencia.refresh_from_db()
        self.assertEqual(esperado.regional, self.base)
        self.assertEqual(divergencia.status, AuditoriaDivergencia.Status.RESOLVIDA)

    def test_transferencia_direta_dispensa_aprovacao_e_resolve_no_recebimento(self):
        equipamento = self.equipamento(base=self.outra_base, sufixo='9')
        SnapshotService.criar_snapshot(self.auditoria, self.user)
        divergencia = LeituraService.registrar(
            auditoria_base=self.auditoria,
            valor=equipamento.patrimonio,
            usuario=self.user,
        ).leitura.divergencias.get()
        EncerramentoService.enviar(self.auditoria, self.user)
        ApuracaoService.solicitar_correcao(
            self.auditoria,
            self.admin,
            prazo_correcao_em=timezone.now() + timedelta(days=2),
            orientacoes='Criar transferência para o destino correto.',
        )
        transferencia = RegularizacaoService.transferir(
            divergencia=divergencia,
            base_destino=self.destino,
            usuario=self.user,
            justificativa='Encaminhar ao destino operacional correto.',
        )
        self.assertTrue(transferencia.aprovacao_admin_dispensada)
        self.assertEqual(transferencia.origem_fluxo, 'AUDITORIA_DIVERGENCIA')
        divergencia.refresh_from_db()
        self.assertEqual(divergencia.status, AuditoriaDivergencia.Status.AGUARDANDO_TRANSFERENCIA)
        enviar_transferencia(transferencia, self.user)
        receber_transferencia(transferencia, self.user)
        divergencia.refresh_from_db()
        equipamento.refresh_from_db()
        self.assertEqual(divergencia.status, AuditoriaDivergencia.Status.RESOLVIDA)
        self.assertEqual(equipamento.regional, self.destino)

    def test_relatorio_base_contem_equipamentos_e_divergencias_detalhadas(self):
        equipamento = self.equipamento()
        SnapshotService.criar_snapshot(self.auditoria, self.user)
        EncerramentoService.enviar(self.auditoria, self.user)
        titulo, linhas = RelatorioService.dados_base(self.auditoria)
        conteudo = '\n'.join(';'.join(str(valor) for valor in linha) for linha in linhas)
        self.assertIn('Equipamentos auditados', conteudo)
        self.assertIn('Divergências detalhadas', conteudo)
        self.assertIn('Ação necessária', conteudo)
        self.assertIn('Sim — correção necessária', conteudo)
        self.assertIn(equipamento.codigo, conteudo)
        self.assertIn(equipamento.patrimonio, conteudo)
        self.assertIn(equipamento.numero_serie, conteudo)
        self.assertEqual(titulo, f'Auditoria - {self.base.nome}')
        arquivo, content_type = RelatorioService.exportar(titulo, linhas, 'xlsx')
        self.assertTrue(arquivo)
        self.assertTrue(content_type)
        with self.assertRaises(ValueError):
            RelatorioService.exportar(titulo, linhas, 'pdf')

    def test_nao_cadastrado_exibe_identificador_informado_na_tela_e_relatorio(self):
        identificador = 'PATRIMONIO-NAO-CADASTRADO-987'
        SnapshotService.criar_snapshot(self.auditoria, self.user)
        leitura = LeituraService.registrar(
            auditoria_base=self.auditoria,
            valor=identificador,
            usuario=self.user,
        ).leitura
        divergencia = leitura.divergencias.get(
            tipo=AuditoriaDivergencia.Tipo.NAO_CADASTRADO,
        )

        self.assertEqual(divergencia.identificador_informado, identificador)
        self.assertIn(identificador, divergencia.descricao)

        _, linhas = RelatorioService.dados_base(self.auditoria)
        cabecalho = next(linha for linha in linhas if linha and linha[0] == 'Tipo')
        linha = next(linha for linha in linhas if linha and linha[0] == 'Não cadastrado')
        self.assertEqual(
            linha[cabecalho.index('Identificador informado')],
            identificador,
        )

        self.client.force_login(self.admin)
        resposta = self.client.get(
            f'/auditorias/divergencias/{divergencia.pk}/',
        )
        self.assertContains(resposta, identificador)

    def test_interface_exibe_voltar_reabrir_finalizar_e_status_dos_equipamentos(self):
        esperado = self.equipamento()
        encontrado_outra_base = self.equipamento(base=self.outra_base, sufixo='2')
        SnapshotService.criar_snapshot(self.auditoria, self.user)
        divergencia = LeituraService.registrar(
            auditoria_base=self.auditoria,
            valor=encontrado_outra_base.patrimonio,
            usuario=self.user,
        ).leitura.divergencias.get()

        self.client.force_login(self.user)
        resposta = self.client.post(
            f'/auditorias/bases/{self.auditoria.pk}/enviar/',
            {'confirmar_envio': '1'},
        )
        self.assertEqual(resposta.status_code, 302)

        self.client.force_login(self.admin)
        resposta = self.client.get(f'/auditorias/bases/{self.auditoria.pk}/divergencias/')
        self.assertContains(resposta, 'Validar resultado')
        self.assertContains(resposta, 'Solicitar correções')
        self.assertContains(resposta, 'Reabrir coleta')
        self.assertContains(resposta, '← Voltar')

        resposta = self.client.get(f'/auditorias/divergencias/{divergencia.pk}/')
        self.assertNotContains(resposta, 'Manter na base encontrada')
        self.client.post(
            f'/auditorias/bases/{self.auditoria.pk}/solicitar-correcao/',
            {
                'prazo_correcao_em': (timezone.localtime() + timedelta(days=2)).strftime('%Y-%m-%dT%H:%M'),
                'orientacoes_correcao': 'Regularizar divergências.',
            },
        )
        resposta = self.client.get(f'/auditorias/divergencias/{divergencia.pk}/')
        self.assertContains(resposta, 'Manter na base encontrada')

        resposta = self.client.get(f'/auditorias/bases/{self.auditoria.pk}/coleta/')
        self.assertContains(resposta, esperado.patrimonio)
        self.assertContains(resposta, 'Status no início')
        self.assertContains(resposta, 'Status atual')
        self.assertContains(resposta, '← Voltar')

    def test_coleta_e_resultado_sao_cegos_para_gestor_ate_finalizacao(self):
        esperado = self.equipamento()
        SnapshotService.criar_snapshot(self.auditoria, self.user)

        self.client.force_login(self.user)
        resposta = self.client.get(f'/auditorias/bases/{self.auditoria.pk}/coleta/')
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Auditoria às cegas')
        self.assertNotContains(resposta, esperado.patrimonio)
        self.assertNotContains(resposta, esperado.numero_serie)
        self.assertNotContains(resposta, 'Não lido')
        self.assertNotContains(resposta, 'Esperados localizados')

        resposta = self.client.post(
            f'/auditorias/bases/{self.auditoria.pk}/leituras/',
            data=json.dumps({'valor': esperado.patrimonio, 'idempotency_key': str(uuid.uuid4())}),
            content_type='application/json',
        )
        self.assertEqual(resposta.status_code, 201)
        dados = resposta.json()
        self.assertEqual(dados['mensagem'], 'Leitura registrada para apuração do administrador.')
        self.assertNotIn('classificacao', dados)
        self.assertNotIn('equipamento', dados)

        envio = self.client.post(
            f'/auditorias/bases/{self.auditoria.pk}/enviar/',
            {'confirmar_envio': '1'},
        )
        self.assertRedirects(
            envio,
            f'/auditorias/bases/{self.auditoria.pk}/coleta/',
        )
        resposta = self.client.get(f'/auditorias/bases/{self.auditoria.pk}/coleta/')
        self.assertContains(resposta, 'A coleta foi enviada e está em apuração pelo administrador.')
        self.assertEqual(
            self.client.get(f'/auditorias/bases/{self.auditoria.pk}/divergencias/').status_code,
            403,
        )
        self.assertEqual(
            self.client.get(f'/auditorias/bases/{self.auditoria.pk}/relatorio.xlsx').status_code,
            403,
        )

        self.client.force_login(self.admin)
        resposta = self.client.get(f'/auditorias/bases/{self.auditoria.pk}/coleta/')
        self.assertContains(resposta, esperado.patrimonio)
        self.client.post(
            f'/auditorias/bases/{self.auditoria.pk}/finalizar/',
            {'confirmar_validacao': '1'},
        )

        self.client.force_login(self.user)
        self.assertEqual(
            self.client.get(f'/auditorias/bases/{self.auditoria.pk}/divergencias/').status_code,
            200,
        )
        self.assertEqual(
            self.client.get(f'/auditorias/bases/{self.auditoria.pk}/relatorio.xlsx').status_code,
            200,
        )

    def test_resultado_legado_sem_finalizacao_admin_permanece_oculto(self):
        self.equipamento()
        SnapshotService.criar_snapshot(self.auditoria, self.user)
        EncerramentoService.enviar(self.auditoria, self.user)
        self.auditoria.status = AuditoriaBase.Status.COM_DIVERGENCIAS
        self.auditoria.finalizada_em = None
        self.auditoria.finalizada_por = None
        self.auditoria.save(update_fields=['status', 'finalizada_em', 'finalizada_por'])

        self.client.force_login(self.user)
        resposta = self.client.get(f'/auditorias/bases/{self.auditoria.pk}/coleta/')
        self.assertContains(resposta, 'Em apuração')
        self.assertNotContains(resposta, 'Com divergências')
        self.assertEqual(
            self.client.get(f'/auditorias/bases/{self.auditoria.pk}/divergencias/').status_code,
            403,
        )

        self.client.force_login(self.admin)
        resposta = self.client.get(f'/auditorias/bases/{self.auditoria.pk}/divergencias/')
        self.assertContains(resposta, 'Validar resultado')

    def test_correcao_libera_divergencia_para_justificativa_mas_nao_relatorio(self):
        self.equipamento()
        SnapshotService.criar_snapshot(self.auditoria, self.user)
        EncerramentoService.enviar(self.auditoria, self.user)
        divergencia = self.auditoria.divergencias.get(tipo=AuditoriaDivergencia.Tipo.NAO_LOCALIZADO)
        prazo = timezone.now() + timedelta(days=3)
        ApuracaoService.solicitar_correcao(
            self.auditoria,
            self.admin,
            prazo_correcao_em=prazo,
            orientacoes='Justificar a ausência e informar as providências.',
        )

        self.client.force_login(self.user)
        resposta = self.client.get(f'/auditorias/bases/{self.auditoria.pk}/divergencias/')
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Justificar a ausência')
        self.assertEqual(
            self.client.get(f'/auditorias/bases/{self.auditoria.pk}/relatorio.xlsx').status_code,
            403,
        )
        resposta = self.client.post(
            f'/auditorias/divergencias/{divergencia.pk}/responder/',
            {'justificativa_base': 'Equipamento encaminhado para busca no depósito.'},
        )
        self.assertEqual(resposta.status_code, 302)
        divergencia.refresh_from_db()
        self.assertEqual(divergencia.status, AuditoriaDivergencia.Status.EM_ANALISE)
        self.assertEqual(divergencia.respondida_por, self.user)
        self.assertIn('busca no depósito', divergencia.justificativa_base)

    def test_validacao_inativa_nao_localizado_na_mesma_base_e_libera_relatorio_final(self):
        equipamento = self.equipamento()
        SnapshotService.criar_snapshot(self.auditoria, self.user)
        EncerramentoService.enviar(self.auditoria, self.user)

        self.client.force_login(self.admin)
        parcial_xlsx = self.client.get(f'/auditorias/bases/{self.auditoria.pk}/relatorio.xlsx')
        self.assertEqual(parcial_xlsx.status_code, 200)
        self.assertIn('parcial.xlsx', parcial_xlsx['Content-Disposition'])
        self.assertEqual(
            self.client.get(f'/auditorias/bases/{self.auditoria.pk}/relatorio.pdf').status_code,
            404,
        )

        resposta = self.client.post(
            f'/auditorias/bases/{self.auditoria.pk}/finalizar/',
            {'confirmar_validacao': '1'},
        )
        self.assertEqual(resposta.status_code, 302)
        equipamento.refresh_from_db()
        self.auditoria.refresh_from_db()
        divergencia = self.auditoria.divergencias.get(tipo=AuditoriaDivergencia.Tipo.NAO_LOCALIZADO)
        self.assertEqual(equipamento.status, 'INATIVO')
        self.assertEqual(equipamento.regional, self.base)
        self.assertEqual(self.auditoria.status, AuditoriaBase.Status.FINALIZADA)
        self.assertIsNotNone(self.auditoria.finalizada_em)
        self.assertEqual(divergencia.status, AuditoriaDivergencia.Status.RESOLVIDA)
        self.assertTrue(hasattr(divergencia, 'resolucao'))

        self.client.force_login(self.user)
        final = self.client.get(f'/auditorias/bases/{self.auditoria.pk}/relatorio.xlsx')
        self.assertEqual(final.status_code, 200)
        self.assertIn('final.xlsx', final['Content-Disposition'])
