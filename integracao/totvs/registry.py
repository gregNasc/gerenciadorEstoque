from integracao.exceptions import TotvsUnsupportedProductError


class TotvsAdapterRegistry:
    _adapters = {}

    @classmethod
    def register(cls, produto, factory):
        cls._adapters[str(produto).strip().upper()] = factory

    @classmethod
    def unregister(cls, produto):
        cls._adapters.pop(str(produto).strip().upper(), None)

    @classmethod
    def supports(cls, produto):
        return str(produto).strip().upper() in cls._adapters

    @classmethod
    def build(cls, produto):
        key = str(produto).strip().upper()
        try:
            factory = cls._adapters[key]
        except KeyError as exc:
            raise TotvsUnsupportedProductError(
                'Ainda não existe adaptador para o produto TOTVS confirmado.'
            ) from exc
        return factory()
