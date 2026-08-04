import hashlib
import tempfile
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from estoque.models import (
    Base,
    Comunicado,
    ComunicadoEntrega,
    DeclaracaoCorreios,
    Emprestimo,
    EnderecoPostalBase,
    Empresa,
    Equipamento,
    GrupoRegional,
    Produto,
    Transferencia,
    TransferenciaItem,
)
from estoque.services.comunicacoes.dispatcher import ComunicacaoDispatcher
from estoque.services.declaracao_correios_service import DeclaracaoCorreiosService


class EstoqueNovasFuncionalidadesTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nome='Empresa')
        self.grupo = GrupoRegional.objects.create(nome='Grupo')
        self.origem = Base.objects.create(empresa=self.empresa, nome='Origem', grupo_regional=self.grupo)
        self.destino = Base.objects.create(empresa=self.empresa, nome='Destino', grupo_regional=self.grupo)
        for base, cidade in ((self.origem, 'Bauru'), (self.destino, 'Campinas')):
            EnderecoPostalBase.objects.create(
                base=base,
                nome_destinatario=base.nome,
                logradouro='Rua Teste',
                numero='10',
                bairro='Centro',
                cidade=cidade,
                uf='SP',
                cep='17000-000',
                documento='12.345.678/0001-90',
            )
        self.user = User.objects.create_user('usuario', password='teste')
        self.user.perfil.role = 'gestor'
        self.user.perfil.empresa = self.empresa
        self.user.perfil.save()
        self.user.perfil.regionais.add(self.origem, self.destino)
        produto = Produto.objects.create(
            codigo='P1', descricao='Coletor Zebra', fabricante='Zebra', modelo='TC', categoria='Coletores'
        )
        self.equipamento = Equipamento.objects.create(
            produto=produto,
            numero_serie='SERIE1',
            patrimonio='PAT1',
            codigo='EQP-1',
            regional=self.origem,
        )
        self.transferencia = Transferencia.objects.create(
            protocolo='TR-001',
            solicitado_por=self.user,
            regional_origem=self.origem,
            regional_destino=self.destino,
        )
        TransferenciaItem.objects.create(transferencia=self.transferencia, equipamento=self.equipamento)

    def test_declaracao_exige_exatamente_uma_operacao(self):
        declaracao = DeclaracaoCorreios(
            tipo_operacao=DeclaracaoCorreios.TipoOperacao.TRANSFERENCIA,
            gerada_por=self.user,
        )
        with self.assertRaises(ValidationError):
            declaracao.full_clean()

    def test_links_de_rastreio_usam_a_consulta_oficial_dos_correios(self):
        self.transferencia.codigo_rastreio = 'AA123456789BR'
        self.transferencia.save(update_fields=['codigo_rastreio'])
        emprestimo = Emprestimo.objects.create(
            protocolo='EMP-RASTREIO',
            grupo=self.grupo,
            regional_origem=self.origem,
            regional_destino=self.destino,
            solicitado_por=self.user,
            motivo='Teste',
            data_emprestimo='2026-08-04',
            data_prevista_devolucao='2026-08-10',
            codigo_rastreio_envio='BB123456789BR',
            codigo_rastreio_devolucao='CC123456789BR',
        )

        self.assertIn('objetos=AA123456789BR', self.transferencia.url_rastreio)
        self.assertIn('objetos=BB123456789BR', emprestimo.url_rastreio_envio)
        self.assertIn('objetos=CC123456789BR', emprestimo.url_rastreio_devolucao)

    @override_settings(MEDIA_ROOT=tempfile.gettempdir())
    def test_declaracao_editavel_emite_pdf_com_hash_e_preserva_versoes(self):
        declaracao = DeclaracaoCorreiosService.criar_rascunho(
            usuario=self.user,
            transferencia=self.transferencia,
        )
        declaracao.peso_total_kg = Decimal('1.250')
        declaracao.valor_total_declarado = Decimal('500.00')
        declaracao.destinatario['nome_destinatario'] = 'Destino editado somente no documento'
        declaracao.save()
        with patch.object(
            DeclaracaoCorreiosService,
            '_desenhar_valores_modelo_oficial',
            wraps=DeclaracaoCorreiosService._desenhar_valores_modelo_oficial,
        ) as desenhar_valores, patch.object(
            DeclaracaoCorreiosService,
            '_texto_ajustado',
            wraps=DeclaracaoCorreiosService._texto_ajustado,
        ) as texto_ajustado:
            emitida = DeclaracaoCorreiosService.emitir_pdf(declaracao, self.user)
        self.assertEqual(desenhar_valores.call_count, 1, 'A declaração deve ter somente uma via por página.')
        chamadas_documento = [
            chamada.args
            for chamada in texto_ajustado.call_args_list
            if len(chamada.args) >= 5 and chamada.args[1] == '12.345.678/0001-90'
        ]
        self.assertEqual([argumentos[2] for argumentos in chamadas_documento], [202.0, 482.5])
        self.assertTrue(all(argumentos[4] == 84.0 for argumentos in chamadas_documento))
        with emitida.arquivo.open('rb') as arquivo:
            conteudo = arquivo.read()
        self.assertTrue(conteudo.startswith(b'%PDF'))
        self.assertEqual(emitida.hash_arquivo, hashlib.sha256(conteudo).hexdigest())
        self.destino.refresh_from_db()
        self.assertEqual(self.destino.nome, 'Destino')
        nova = DeclaracaoCorreiosService.substituir(emitida, {}, self.user)
        self.assertEqual(nova.versao, 2)
        emitida.refresh_from_db()
        self.assertEqual(emitida.status, DeclaracaoCorreios.Status.SUBSTITUIDA)

    @override_settings(WHATSAPP_ENABLED=False)
    def test_whatsapp_desabilitado_mantem_entrega_interna(self):
        comunicado = Comunicado.objects.create(
            titulo='Aviso', mensagem='Teste', criado_por=self.user, empresa=self.empresa
        )
        comunicado.usuarios.add(self.user)
        ComunicacaoDispatcher.criar_entregas(comunicado.pk)
        self.assertTrue(comunicado.entregas.filter(canal=ComunicadoEntrega.Canal.SISTEMA).exists())
        self.assertFalse(comunicado.entregas.filter(canal=ComunicadoEntrega.Canal.WHATSAPP).exists())
