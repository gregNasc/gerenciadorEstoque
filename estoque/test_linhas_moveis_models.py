from datetime import timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from compras.models import (
    CapacidadeCatalogoProdutoEmpresa,
    CatalogoProdutoEmpresa,
)
from estoque.models import (
    Base,
    Empresa,
    Equipamento,
    HistoricoLinhaMovel,
    LinhaMovel,
    OperadoraMovel,
    Produto,
    VinculoLinhaEquipamento,
)


class LinhasMoveisModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa_a = Empresa.objects.create(nome='Tenant Linhas A')
        cls.empresa_b = Empresa.objects.create(nome='Tenant Linhas B')
        cls.base_a = Base.objects.create(nome='Base A', empresa=cls.empresa_a)
        cls.base_a_2 = Base.objects.create(nome='Base A 2', empresa=cls.empresa_a)
        cls.base_b = Base.objects.create(nome='Base B', empresa=cls.empresa_b)
        cls.usuario = User.objects.create_user(username='autor_linhas')
        cls.operadora_a = OperadoraMovel.objects.create(
            empresa=cls.empresa_a,
            nome='Operadora A',
        )
        cls.operadora_b = OperadoraMovel.objects.create(
            empresa=cls.empresa_b,
            nome='Operadora B',
        )
        cls.produto = Produto.objects.create(
            codigo='MOV-R1-A',
            descricao='Equipamento com conectividade móvel',
            fabricante='Fabricante',
            modelo='Modelo móvel',
            categoria='Categoria configurável',
        )
        cls.catalogo_a = CatalogoProdutoEmpresa.objects.create(
            empresa=cls.empresa_a,
            produto=cls.produto,
        )
        cls.catalogo_b = CatalogoProdutoEmpresa.objects.create(
            empresa=cls.empresa_b,
            produto=cls.produto,
        )
        cls.capacidade_a = CapacidadeCatalogoProdutoEmpresa.objects.create(
            catalogo=cls.catalogo_a,
            codigo='conectividade_movel',
            configurado_por=cls.usuario,
        )
        cls.equipamento_a = Equipamento.objects.create(
            produto=cls.produto,
            numero_serie='SERIE-MOV-R1-A',
            patrimonio='PAT-MOV-R1-A',
            regional=cls.base_a,
            codigo='EQ-MOV-R1-A',
        )
        cls.equipamento_a_2 = Equipamento.objects.create(
            produto=cls.produto,
            numero_serie='SERIE-MOV-R1-A2',
            patrimonio='PAT-MOV-R1-A2',
            regional=cls.base_a,
            codigo='EQ-MOV-R1-A2',
        )
        cls.equipamento_a_base_2 = Equipamento.objects.create(
            produto=cls.produto,
            numero_serie='SERIE-MOV-R1-A3',
            patrimonio='PAT-MOV-R1-A3',
            regional=cls.base_a_2,
            codigo='EQ-MOV-R1-A3',
        )
        cls.equipamento_b = Equipamento.objects.create(
            produto=cls.produto,
            numero_serie='SERIE-MOV-R1-B',
            patrimonio='PAT-MOV-R1-B',
            regional=cls.base_b,
            codigo='EQ-MOV-R1-B',
        )

    def criar_linha(self, *, numero='+5511999990001', iccid='8955012345678901234'):
        return LinhaMovel.objects.create(
            empresa=self.empresa_a,
            base=self.base_a,
            numero_normalizado=numero,
            operadora=self.operadora_a,
            iccid=iccid,
            criado_por=self.usuario,
        )

    def test_capacidade_e_normalizada_e_isolada_por_catalogo_do_tenant(self):
        self.capacidade_a.refresh_from_db()

        self.assertEqual(
            self.capacidade_a.codigo,
            CapacidadeCatalogoProdutoEmpresa.CONECTIVIDADE_MOVEL,
        )
        self.assertTrue(
            CapacidadeCatalogoProdutoEmpresa.objects.filter(
                catalogo__empresa=self.empresa_a,
                catalogo__produto=self.produto,
                codigo='CONECTIVIDADE_MOVEL',
                ativa=True,
            ).exists()
        )
        self.assertFalse(
            CapacidadeCatalogoProdutoEmpresa.objects.filter(
                catalogo__empresa=self.empresa_b,
                catalogo__produto=self.produto,
                codigo='CONECTIVIDADE_MOVEL',
                ativa=True,
            ).exists()
        )

    def test_numero_e_iccid_sao_unicos_somente_dentro_da_empresa(self):
        linha_a = self.criar_linha()
        LinhaMovel.objects.create(
            empresa=self.empresa_b,
            base=self.base_b,
            numero_normalizado=linha_a.numero_normalizado,
            operadora=self.operadora_b,
            iccid=linha_a.iccid,
            criado_por=self.usuario,
        )

        with self.assertRaises(ValidationError):
            self.criar_linha(numero=linha_a.numero_normalizado, iccid='8955012345678909999')
        with self.assertRaises(ValidationError):
            self.criar_linha(numero='+5511999990002', iccid=linha_a.iccid)

    def test_linha_exige_numero_e164_e_iccid_numerico(self):
        with self.assertRaises(ValidationError):
            self.criar_linha(numero='(11) 99999-0001')
        with self.assertRaises(ValidationError):
            self.criar_linha(iccid='ICCID-INVALIDO')

    def test_linha_rejeita_base_e_operadora_de_outro_tenant(self):
        with self.assertRaises(ValidationError) as contexto:
            LinhaMovel.objects.create(
                empresa=self.empresa_a,
                base=self.base_b,
                numero_normalizado='+5511999990003',
                operadora=self.operadora_b,
                criado_por=self.usuario,
            )

        self.assertIn('base', contexto.exception.message_dict)
        self.assertIn('operadora', contexto.exception.message_dict)

    def test_vinculo_requer_mesmo_tenant_base_e_capacidade_ativa(self):
        linha = self.criar_linha()

        with self.assertRaises(ValidationError):
            VinculoLinhaEquipamento.objects.create(
                linha=linha,
                equipamento=self.equipamento_b,
                vinculado_por=self.usuario,
            )
        with self.assertRaises(ValidationError):
            VinculoLinhaEquipamento.objects.create(
                linha=linha,
                equipamento=self.equipamento_a_base_2,
                vinculado_por=self.usuario,
            )

        linha_b = LinhaMovel.objects.create(
            empresa=self.empresa_b,
            base=self.base_b,
            numero_normalizado='+5511999990004',
            operadora=self.operadora_b,
            criado_por=self.usuario,
        )
        with self.assertRaises(ValidationError) as contexto:
            VinculoLinhaEquipamento.objects.create(
                linha=linha_b,
                equipamento=self.equipamento_b,
                vinculado_por=self.usuario,
            )
        self.assertIn('conectividade móvel ativa', str(contexto.exception))

    def test_constraints_impedem_dois_vinculos_ativos(self):
        linha_1 = self.criar_linha()
        linha_2 = self.criar_linha(
            numero='+5511999990005',
            iccid='8955012345678901235',
        )
        VinculoLinhaEquipamento.objects.create(
            linha=linha_1,
            equipamento=self.equipamento_a,
            vinculado_por=self.usuario,
        )

        with self.assertRaises(ValidationError):
            VinculoLinhaEquipamento.objects.create(
                linha=linha_1,
                equipamento=self.equipamento_a_2,
                vinculado_por=self.usuario,
            )
        with self.assertRaises(ValidationError):
            VinculoLinhaEquipamento.objects.create(
                linha=linha_2,
                equipamento=self.equipamento_a,
                vinculado_por=self.usuario,
            )

    def test_constraint_de_banco_protege_vinculo_ativo_sem_depender_do_save(self):
        linha = self.criar_linha()
        VinculoLinhaEquipamento.objects.create(
            linha=linha,
            equipamento=self.equipamento_a,
            vinculado_por=self.usuario,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            VinculoLinhaEquipamento.objects.bulk_create([
                VinculoLinhaEquipamento(
                    linha=linha,
                    equipamento=self.equipamento_a_2,
                    vinculado_por=self.usuario,
                ),
            ])

    def test_vinculo_encerrado_preserva_historico_e_libera_novo_vinculo(self):
        linha = self.criar_linha()
        inicio = timezone.now()
        anterior = VinculoLinhaEquipamento.objects.create(
            linha=linha,
            equipamento=self.equipamento_a,
            inicio_em=inicio,
            vinculado_por=self.usuario,
        )
        anterior.fim_em = inicio + timedelta(minutes=1)
        anterior.motivo_fim = 'Troca controlada'
        anterior.desvinculado_por = self.usuario
        anterior.save()

        atual = VinculoLinhaEquipamento.objects.create(
            linha=linha,
            equipamento=self.equipamento_a_2,
            vinculado_por=self.usuario,
        )

        self.assertEqual(linha.vinculos_equipamento.count(), 2)
        self.assertFalse(anterior.ativo)
        self.assertTrue(atual.ativo)

    def test_periodo_invalido_e_linha_inativa_nao_podem_ser_vinculados(self):
        linha = self.criar_linha()
        agora = timezone.now()
        with self.assertRaises(ValidationError):
            VinculoLinhaEquipamento.objects.create(
                linha=linha,
                equipamento=self.equipamento_a,
                inicio_em=agora,
                fim_em=agora - timedelta(seconds=1),
                vinculado_por=self.usuario,
            )

        linha.status = LinhaMovel.Status.INATIVA
        linha.save()
        with self.assertRaises(ValidationError):
            VinculoLinhaEquipamento.objects.create(
                linha=linha,
                equipamento=self.equipamento_a,
                vinculado_por=self.usuario,
            )

    def test_historico_exige_mesmo_tenant_e_protege_auditoria(self):
        linha = self.criar_linha()
        historico = HistoricoLinhaMovel.objects.create(
            empresa=self.empresa_a,
            linha=linha,
            evento=HistoricoLinhaMovel.Evento.CADASTRO,
            autor=self.usuario,
            metadados={'origem': 'teste'},
        )
        with self.assertRaises(ValidationError):
            HistoricoLinhaMovel.objects.create(
                empresa=self.empresa_b,
                linha=linha,
                evento=HistoricoLinhaMovel.Evento.ALTERACAO,
                autor=self.usuario,
            )
        with self.assertRaises(ProtectedError):
            linha.delete()

        self.assertTrue(HistoricoLinhaMovel.objects.filter(pk=historico.pk).exists())

    def test_historico_rejeita_credenciais_sensiveis_inclusive_aninhadas(self):
        linha = self.criar_linha()

        with self.assertRaises(ValidationError) as contexto:
            HistoricoLinhaMovel.objects.create(
                empresa=self.empresa_a,
                linha=linha,
                evento=HistoricoLinhaMovel.Evento.ALTERACAO,
                autor=self.usuario,
                metadados={'alteracoes': [{'PUK 2': 'conteudo-proibido'}]},
            )

        self.assertIn('metadados', contexto.exception.message_dict)

    def test_modelo_nao_armazena_pin_ou_puk_em_texto_aberto(self):
        campos = {campo.name for campo in LinhaMovel._meta.get_fields()}

        self.assertTrue({'numero_normalizado', 'iccid', 'operadora'} <= campos)
        self.assertTrue({'pin', 'pin2', 'puk', 'puk2'}.isdisjoint(campos))


class LinhasMoveisMigrationTests(TransactionTestCase):
    migrate_from = [
        ('compras', '0003_catalogoprodutoempresa'),
        ('estoque', '0058_secao_documentacao_legado_explicito'),
    ]
    migrate_to = [
        ('compras', '0004_capacidadecatalogoprodutoempresa'),
        ('estoque', '0060_credenciallinhamovel'),
    ]
    tabelas_r1 = {
        'compras_capacidadecatalogoprodutoempresa',
        'estoque_operadoramovel',
        'estoque_linhamovel',
        'estoque_vinculolinhaequipamento',
        'estoque_historicolinhamovel',
        'estoque_credenciallinhamovel',
    }

    def test_migrations_sao_reversiveis_e_reaplicaveis(self):
        executor = MigrationExecutor(connection)
        try:
            executor.migrate(self.migrate_from)
            tabelas_apos_reversao = set(connection.introspection.table_names())
            self.assertTrue(self.tabelas_r1.isdisjoint(tabelas_apos_reversao))
        finally:
            MigrationExecutor(connection).migrate(self.migrate_to)

        tabelas_apos_reaplicacao = set(connection.introspection.table_names())
        self.assertTrue(self.tabelas_r1 <= tabelas_apos_reaplicacao)
