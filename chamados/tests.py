from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from chamados.models import CategoriaChamado, Chamado, ChamadoAnexo, ChamadoMensagem
from chamados.policies import ChamadoAccessPolicy
from chamados.services import ChamadoService
from estoque.models import Base, Comunicado, Empresa, Perfil


class ChamadosIntegracaoTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nome='Empresa Principal')
        self.base = Base.objects.create(empresa=self.empresa, nome='Base Curitiba')
        self.outra_base = Base.objects.create(empresa=self.empresa, nome='Base Recife')
        self.solicitante = User.objects.create_user('solicitante', password='SenhaForte123!')
        self.solicitante.perfil.empresa = self.empresa
        self.solicitante.perfil.role = Perfil.Role.OPERADOR
        self.solicitante.perfil.save()
        self.solicitante.perfil.regionais.add(self.base)
        self.outro = User.objects.create_user('outro', password='SenhaForte123!')
        self.outro.perfil.empresa = self.empresa
        self.outro.perfil.role = Perfil.Role.OPERADOR
        self.outro.perfil.save()
        self.outro.perfil.regionais.add(self.outra_base)
        self.admin = User.objects.create_user('admin_chamados', password='SenhaForte123!')
        self.admin.perfil.empresa = self.empresa
        self.admin.perfil.role = Perfil.Role.ADMIN
        self.admin.perfil.save()
        self.atendente = User.objects.create_user('atendente', password='SenhaForte123!')
        self.atendente.perfil.empresa = self.empresa
        self.atendente.perfil.regionais.add(self.base)
        self.atendente.groups.add(Group.objects.get(name=ChamadoAccessPolicy.GRUPO_ATENDIMENTO))
        self.categoria = CategoriaChamado.objects.get(nome='ROUTER NÃO FUNCIONA')

    def abrir(self):
        return ChamadoService.abrir(
            usuario=self.solicitante,
            base=self.base,
            inventario=None,
            categoria=self.categoria,
            loja='Loja Centro',
            lider='Maria Souza',
            titulo='Sem conexão no inventário',
            descricao='Router não liga e a equipe está parada.',
            prioridade=Chamado.Prioridade.CRITICA,
        )

    def test_abertura_usa_usuarios_bases_e_comunicados_do_gerenciador(self):
        chamado = self.abrir()

        self.assertRegex(chamado.protocolo, r'^CH-\d{4}-\d{4}-000001$')
        self.assertEqual(chamado.titulo, 'SEM CONEXÃO NO INVENTÁRIO')
        self.assertEqual(chamado.loja, 'LOJA CENTRO')
        self.assertEqual(chamado.empresa, self.empresa)
        self.assertEqual(chamado.base, self.base)
        comunicado = Comunicado.objects.get(dados__chamado_id=chamado.pk)
        self.assertTrue(comunicado.usuarios.filter(pk=self.admin.pk).exists())
        self.assertTrue(comunicado.usuarios.filter(pk=self.solicitante.pk).exists())

    def test_isola_chamado_de_usuario_sem_acesso(self):
        chamado = self.abrir()
        self.client.force_login(self.outro)

        response = self.client.get(reverse('chamados:detalhe', args=[chamado.pk]))

        self.assertEqual(response.status_code, 404)

    def test_atendente_assume_conversa_e_resolve_com_historico(self):
        chamado = self.abrir()
        ChamadoService.assumir(chamado, self.atendente)
        mensagem = ChamadoService.adicionar_mensagem(
            chamado, self.atendente, 'Reiniciamos o equipamento e validamos a rede.'
        )
        ChamadoService.alterar_status(
            chamado,
            self.atendente,
            Chamado.Status.RESOLVIDO,
            'Equipamento reiniciado e conexão restabelecida.',
        )
        chamado.refresh_from_db()

        self.assertEqual(chamado.atendente, self.atendente)
        self.assertEqual(chamado.status, Chamado.Status.RESOLVIDO)
        self.assertEqual(mensagem.texto, 'REINICIAMOS O EQUIPAMENTO E VALIDAMOS A REDE.')
        self.assertGreaterEqual(chamado.eventos.count(), 4)

    def test_nota_interna_nao_e_exibida_ao_solicitante(self):
        chamado = self.abrir()
        ChamadoService.assumir(chamado, self.atendente)
        ChamadoService.adicionar_mensagem(
            chamado, self.atendente, 'Possível troca em garantia.', nota_interna=True
        )
        self.client.force_login(self.solicitante)

        response = self.client.get(reverse('chamados:detalhe', args=[chamado.pk]))

        self.assertNotContains(response, 'POSSÍVEL TROCA EM GARANTIA')
        self.assertFalse(response.context['mensagens_chamado'].filter(nota_interna=True).exists())
        comunicado_nota = Comunicado.objects.filter(
            dados__chamado_id=chamado.pk,
            mensagem='UMA NOTA INTERNA FOI REGISTRADA.',
        ).latest('pk')
        self.assertFalse(comunicado_nota.usuarios.filter(pk=self.solicitante.pk).exists())
        self.assertTrue(comunicado_nota.usuarios.filter(pk=self.admin.pk).exists())

    def test_usuario_comum_nao_assume_nem_cria_nota_interna(self):
        chamado = self.abrir()
        with self.assertRaises(PermissionDenied):
            ChamadoService.assumir(chamado, self.solicitante)
        with self.assertRaises(PermissionDenied):
            ChamadoService.adicionar_mensagem(
                chamado, self.solicitante, 'Nota indevida', nota_interna=True
            )

    def test_anexo_com_extensao_nao_permitida_e_bloqueado(self):
        chamado = self.abrir()
        arquivo = SimpleUploadedFile('programa.exe', b'conteudo', content_type='application/octet-stream')

        with self.assertRaises(ValidationError):
            ChamadoService.adicionar_mensagem(
                chamado, self.solicitante, 'Segue o arquivo.', anexo=arquivo
            )

        self.assertFalse(ChamadoAnexo.objects.exists())

    def test_rotas_de_lista_dashboard_e_exportacao_respeitam_perfis(self):
        self.abrir()
        self.client.force_login(self.solicitante)
        self.assertEqual(self.client.get(reverse('chamados:lista')).status_code, 200)
        self.assertEqual(self.client.get(reverse('chamados:dashboard')).status_code, 200)
        self.assertEqual(self.client.get(reverse('chamados:exportar')).status_code, 403)

        self.client.force_login(self.admin)
        response = self.client.get(reverse('chamados:exportar'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def test_solicitante_fecha_chamado_resolvido(self):
        chamado = self.abrir()
        ChamadoService.assumir(chamado, self.admin)
        ChamadoService.alterar_status(
            chamado, self.admin, Chamado.Status.RESOLVIDO, 'Acesso normalizado.'
        )

        ChamadoService.alterar_status(
            chamado, self.solicitante, Chamado.Status.FECHADO, 'Solução confirmada.'
        )
        chamado.refresh_from_db()
        self.assertEqual(chamado.status, Chamado.Status.FECHADO)

    def test_protocolos_sao_unicos_entre_empresas(self):
        primeiro = self.abrir()
        outra_empresa = Empresa.objects.create(nome='Outra Empresa')
        base = Base.objects.create(empresa=outra_empresa, nome='Base Matriz')

        segundo = ChamadoService.abrir(
            usuario=self.admin,
            base=base,
            inventario=None,
            categoria=self.categoria,
            loja='',
            lider='',
            titulo='Falha geral',
            descricao='Teste de protocolo entre empresas.',
            prioridade=Chamado.Prioridade.NORMAL,
        )

        self.assertNotEqual(primeiro.protocolo, segundo.protocolo)
