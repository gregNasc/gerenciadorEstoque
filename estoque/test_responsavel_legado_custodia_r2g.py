from estoque import test_itens_custodia_r2e as r2e_tests
from estoque.models import Colaborador, Custodia, Equipamento, ItemCustodia
from estoque.services.custodia_responsavel_legado_service import (
    CustodiaResponsavelLegadoService,
)


class ResponsavelLegadoCustodiaR2GTests(r2e_tests.ItensCustodiaR2ETests):
    def test_custodia_vigente_espelha_colaborador_no_campo_legado(self):
        ItemCustodia.objects.create(
            custodia=self.custodia,
            equipamento=self.equipamento,
        )
        self.equipamento.refresh_from_db()

        self.assertEqual(self.equipamento.responsavel, self.colaborador.nome)

    def test_finalizacao_libera_valor_gerenciado_sem_apagar_historico(self):
        item = ItemCustodia.objects.create(
            custodia=self.custodia,
            equipamento=self.equipamento,
        )
        self.custodia.status = Custodia.Status.FINALIZADA
        self.custodia.save()
        self.equipamento.refresh_from_db()

        self.assertEqual(self.equipamento.responsavel, '')
        self.assertTrue(ItemCustodia.objects.filter(pk=item.pk).exists())

    def test_valor_legado_manual_divergente_nao_e_apagado(self):
        ItemCustodia.objects.create(
            custodia=self.custodia,
            equipamento=self.equipamento,
        )
        Equipamento.objects.filter(pk=self.equipamento.pk).update(
            responsavel='RESPONSÁVEL LEGADO MANUAL',
        )
        self.custodia.status = Custodia.Status.FINALIZADA
        self.custodia.save()
        self.equipamento.refresh_from_db()

        self.assertEqual(
            self.equipamento.responsavel,
            'RESPONSÁVEL LEGADO MANUAL',
        )

    def test_equipamento_sem_custodia_preserva_responsavel_legado(self):
        Equipamento.objects.filter(pk=self.equipamento.pk).update(
            responsavel='RESPONSÁVEL ANTERIOR',
        )
        self.equipamento.refresh_from_db()

        self.assertEqual(
            CustodiaResponsavelLegadoService.responsavel_atual(self.equipamento),
            'RESPONSÁVEL ANTERIOR',
        )

    def test_resolvedor_prefere_colaborador_da_custodia_vigente(self):
        ItemCustodia.objects.create(
            custodia=self.custodia,
            equipamento=self.equipamento,
        )
        Equipamento.objects.filter(pk=self.equipamento.pk).update(
            responsavel='VALOR DESATUALIZADO',
        )
        self.equipamento.refresh_from_db()

        self.assertEqual(
            CustodiaResponsavelLegadoService.responsavel_atual(self.equipamento),
            self.colaborador.nome,
        )

    def test_troca_do_colaborador_sincroniza_custodia_vigente(self):
        ItemCustodia.objects.create(
            custodia=self.custodia,
            equipamento=self.equipamento,
        )
        novo_colaborador = Colaborador.objects.create(
            empresa=self.empresa,
            base=self.base,
            nome='Novo Colaborador Custódia',
        )
        self.custodia.colaborador = novo_colaborador
        self.custodia.save()
        self.equipamento.refresh_from_db()

        self.assertEqual(self.equipamento.responsavel, novo_colaborador.nome)
