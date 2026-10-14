from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from estoque.models import Custodia, ItemCustodia
from estoque import test_itens_custodia_r2e as r2e_tests


class ExclusividadeCustodiaR2FTests(r2e_tests.ItensCustodiaR2ETests):
    def nova_custodia(self, *, status=Custodia.Status.ATIVA):
        return Custodia.objects.create(
            empresa=self.empresa,
            colaborador=self.colaborador,
            base=self.base,
            registrado_por=self.usuario,
            status=status,
        )

    def test_equipamento_nao_pode_estar_em_duas_custodias_vigentes(self):
        ItemCustodia.objects.create(
            custodia=self.custodia,
            equipamento=self.equipamento,
        )
        outra = self.nova_custodia()

        with self.assertRaises(ValidationError):
            ItemCustodia.objects.create(
                custodia=outra,
                equipamento=self.equipamento,
            )

    def test_linha_nao_pode_estar_em_duas_custodias_vigentes(self):
        ItemCustodia.objects.create(
            custodia=self.custodia,
            linha_movel=self.linha,
        )
        outra = self.nova_custodia()

        with self.assertRaises(ValidationError):
            ItemCustodia.objects.create(
                custodia=outra,
                linha_movel=self.linha,
            )

    def test_rascunhos_podem_referenciar_o_mesmo_ativo_sem_reserva(self):
        primeiro = self.nova_custodia(status=Custodia.Status.RASCUNHO)
        segundo = self.nova_custodia(status=Custodia.Status.RASCUNHO)

        item_a = ItemCustodia.objects.create(
            custodia=primeiro,
            equipamento=self.equipamento,
        )
        item_b = ItemCustodia.objects.create(
            custodia=segundo,
            equipamento=self.equipamento,
        )

        self.assertFalse(item_a.vigente)
        self.assertFalse(item_b.vigente)

    def test_ativacao_de_rascunho_com_conflito_e_rejeitada_sem_mudar_status(self):
        ItemCustodia.objects.create(
            custodia=self.custodia,
            equipamento=self.equipamento,
        )
        rascunho = self.nova_custodia(status=Custodia.Status.RASCUNHO)
        ItemCustodia.objects.create(
            custodia=rascunho,
            equipamento=self.equipamento,
        )

        rascunho.status = Custodia.Status.ATIVA
        with self.assertRaises(ValidationError):
            rascunho.save()

        rascunho.refresh_from_db()
        self.assertEqual(rascunho.status, Custodia.Status.RASCUNHO)
        self.assertFalse(rascunho.itens.get().vigente)

    def test_finalizacao_libera_ativo_sem_apagar_historico(self):
        item_antigo = ItemCustodia.objects.create(
            custodia=self.custodia,
            equipamento=self.equipamento,
        )
        self.custodia.status = Custodia.Status.FINALIZADA
        self.custodia.save()
        item_antigo.refresh_from_db()
        self.assertFalse(item_antigo.vigente)

        nova = self.nova_custodia()
        item_novo = ItemCustodia.objects.create(
            custodia=nova,
            equipamento=self.equipamento,
        )

        self.assertTrue(item_novo.vigente)
        self.assertTrue(ItemCustodia.objects.filter(pk=item_antigo.pk).exists())

    def test_em_devolucao_permanece_vigente(self):
        item = ItemCustodia.objects.create(
            custodia=self.custodia,
            equipamento=self.equipamento,
        )
        self.custodia.status = Custodia.Status.EM_DEVOLUCAO
        self.custodia.save()
        item.refresh_from_db()

        self.assertTrue(item.vigente)

    def test_cancelamento_libera_ativo_sem_apagar_historico(self):
        item = ItemCustodia.objects.create(
            custodia=self.custodia,
            linha_movel=self.linha,
        )
        self.custodia.status = Custodia.Status.CANCELADA
        self.custodia.save()
        item.refresh_from_db()

        self.assertFalse(item.vigente)
        self.assertTrue(ItemCustodia.objects.filter(pk=item.pk).exists())

    def test_constraint_do_banco_protege_mesmo_sem_save_do_modelo(self):
        ItemCustodia.objects.create(
            custodia=self.custodia,
            equipamento=self.equipamento,
        )
        outra = self.nova_custodia()
        duplicado = ItemCustodia(
            custodia=outra,
            equipamento=self.equipamento,
            vigente=True,
            descricao_snapshot='Snapshot concorrente',
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ItemCustodia.objects.bulk_create([duplicado])
