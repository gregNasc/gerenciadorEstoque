"""Catálogo visual dos equipamentos exibidos no contexto de chamados.

As imagens apontam para páginas de fabricantes ou catálogos de produto
pesquisados para os modelos existentes. Cadastros sem modelo completo usam
uma imagem representativa da família e são identificados como ilustrativos.
"""


EQUIPMENT_IMAGES = (
    {
        'aliases': ('MOTOROLA MC-65', 'MOTOROLA MC65'),
        'url': 'https://cdn11.bigcommerce.com/s-ftsflnse4o/images/stencil/608x608/products/78664/306321/D_993130-MLB71537388748_092023-O__14452.1730814122.jpg?c=1',
        'source_url': 'https://latinafy.com/products/motorola-mc65-data-collector-mc659b-win-6-5-semi-new/',
        'source_label': 'Motorola MC65',
        'alt': 'Coletor de dados Motorola MC65',
    },
    {
        'aliases': ('UROVO DT-40', 'UROVO DT40'),
        'url': 'https://cdn.awsli.com.br/600x450/1296/1296864/produto/256206391/snapedit_1708536589992-37n5ecsbu8.png',
        'source_url': 'https://www.pontoautomacao.com.br/coletor-dt40-urovo',
        'source_label': 'Urovo DT40',
        'alt': 'Coletor de dados Urovo DT40',
    },
    {
        'aliases': ('SKORPIO X4',),
        'url': 'https://www.discountcreditcardsupply.com/cdn/shop/products/plp_skorpiox4_50key_we_800_700_600x600_crop_center.png?v=1663362647',
        'source_url': 'https://www.discountcreditcardsupply.com/products/datalogic-skorpio-x4-scanner',
        'source_label': 'Datalogic Skorpio X4',
        'alt': 'Coletor de dados Datalogic Skorpio X4',
    },
    {
        'aliases': ('SKORPIO X3',),
        'url': 'https://www.elliaden.com/img/produits/terminal-mobile-datalogic-skorpio-x3-58af25c9f2e4f.jpg',
        'source_url': 'https://www.elliaden.com/terminal-mobile-datalogic-skorpio-x3.html',
        'source_label': 'Datalogic Skorpio X3',
        'alt': 'Coletor de dados Datalogic Skorpio X3',
    },
    {
        'aliases': ('MOBYDATA',),
        'url': 'https://s.alicdn.com/%40sc04/kf/H545c5b4d40bf4a4cb5e7fc33a1d031d7v/Good-Price-2.8Inch-Touch-Screen-Portable-Smart-Android-2D-Barcode-Scanner-Keyboard-Data-Collector-PDA.jpg',
        'source_url': 'https://device.report/mobydata',
        'source_label': 'MobyData',
        'alt': 'Coletor de dados da família MobyData',
        'illustrative': True,
    },
    {
        'aliases': ('BROTHER 1202', 'HL-1202', 'HL1202'),
        'url': 'https://www.brother.com.br/-/media/brother/product-catalog-media/images/2021/11/23/11/22/hl1202_0.png',
        'source_url': 'https://www.brother.com.br/products/HL1202',
        'source_label': 'Brother HL-1202',
        'alt': 'Impressora Brother HL-1202',
    },
    {
        'aliases': ('PANTUM P2500W',),
        'url': 'https://d3rs3wc4pbrcza.cloudfront.net/files/4012/Images/3-4012-737041-310122073412654.jpg',
        'source_url': 'https://global.pantum.com/search/product?s=2500w',
        'source_label': 'Pantum P2500W',
        'alt': 'Impressora Pantum P2500W',
    },
    {
        'aliases': ('XEROX 3020', 'PHASER 3020'),
        'url': 'https://cdn.akakce.com/_static/371474986/xerox-phaser-3020.jpg',
        'source_url': 'https://www.xerox.com/en-bh/office/printers/phaser-3020',
        'source_label': 'Xerox Phaser 3020',
        'alt': 'Impressora Xerox Phaser 3020',
    },
    {
        'aliases': ('HP LASER',),
        'url': 'https://kompacits.ae/cdn/shop/files/4ZB78A.webp?v=1750782050',
        'source_url': 'https://support.hp.com/us-en/product/product-specs/hp/24494342',
        'source_label': 'HP Laser 107w',
        'alt': 'Impressora da família HP Laser',
        'illustrative': True,
    },
    {
        'aliases': ('DELL INSPIRON 3520',),
        'url': 'https://cdn.mos.cms.futurecdn.net/4xS4ZEe5zANUgRNNNvHV4j.jpg',
        'source_url': 'https://www.dell.com/support/product-details/pt-br/product/inspiron-15-3520-laptop/overview',
        'source_label': 'Dell Inspiron 3520',
        'alt': 'Notebook Dell Inspiron 3520',
    },
    {
        'aliases': ('DELL VOSTRO 15 3510', 'DELL VOSTRO 3510'),
        'url': 'https://www.dellonline.co.za/cdn/shop/products/148DA1B2-D324-4729-874E-B2751495AB76_111466_1800x1800.jpg?v=1655902174',
        'source_url': 'https://www.dell.com/support/product-details/pt-br/product/vostro-15-3510-laptop/overview',
        'source_label': 'Dell Vostro 3510',
        'alt': 'Notebook Dell Vostro 3510',
    },
    {
        'aliases': ('DELL INSPIRON 3000',),
        'url': 'https://i.dell.com/is/image/DellContent//content/dam/ss2/product-images/dell-client-products/notebooks/inspiron-notebooks/inspiron-3501/pdp/notebook_laptop_inspiron_bullseye_intel_pdp_gallery504x350.jpg?qlt=95&fit=constrain,1&hei=400&wid=570&fmt=jpg',
        'source_url': 'https://www.dell.com/en-us/shop/dell-laptops/inspiron-15-3000-laptop/spd/inspiron-15-3501-laptop/nn3501fthzs',
        'source_label': 'Dell Inspiron 3000',
        'alt': 'Notebook da família Dell Inspiron 3000',
        'illustrative': True,
    },
    {
        'aliases': ('LENOVO IDEAPAD 1',),
        'url': 'https://computermania.co.za/cdn/shop/files/82LX00CHSA.1.jpg?v=1748955231',
        'source_url': 'https://www.lenovo.com/br/pt/laptops/ideapad/ideapad-100-series/',
        'source_label': 'Lenovo IdeaPad 1',
        'alt': 'Notebook Lenovo IdeaPad 1',
    },
    {
        'aliases': ('MIKROTIK AC LITE',),
        'url': 'https://cdn.mikrotik.com/web-assets/rb_images/1272_xl.webp',
        'source_url': 'https://mikrotik.com/product/RBcAPL-2nD-307',
        'source_label': 'MikroTik cAP lite',
        'alt': 'Roteador MikroTik cAP lite',
    },
    {
        'aliases': ('MIKROTIK AC PRO',),
        'url': 'https://cdn.mikrotik.com/web-assets/rb_images/1447_xl.webp',
        'source_url': 'https://mikrotik.com/product/cap_ac',
        'source_label': 'MikroTik cAP ac',
        'alt': 'Roteador MikroTik cAP ac',
        'illustrative': True,
    },
    {
        'aliases': ('MIKROTIK AC',),
        'url': 'https://cdn.mikrotik.com/web-assets/rb_images/1447_xl.webp',
        'source_url': 'https://mikrotik.com/product/cap_ac',
        'source_label': 'MikroTik cAP ac',
        'alt': 'Roteador da família MikroTik AC',
        'illustrative': True,
    },
    {
        'aliases': ('TP-LINK TL-WR829N', 'TL-WR829N'),
        'url': 'https://static.tp-link.com/Brazil-TL-WR829N(BR)2.0-230x170x63-L-7022506829_large_1589417963104t.jpg',
        'source_url': 'https://www.tp-link.com/br/home-networking/wifi-router/tl-wr829n/',
        'source_label': 'TP-Link TL-WR829N',
        'alt': 'Roteador TP-Link TL-WR829N',
    },
)


def equipment_image_for(product):
    """Retorna os metadados visuais do produto, se houver correspondência."""
    if not product:
        return None

    searchable = ' '.join(
        str(value or '')
        for value in (
            product.descricao,
            product.fabricante,
            product.modelo,
        )
    ).upper()

    for item in EQUIPMENT_IMAGES:
        if any(alias in searchable for alias in item['aliases']):
            return {
                'url': item['url'],
                'source_url': item['source_url'],
                'source_label': item['source_label'],
                'alt': item['alt'],
                'illustrative': item.get('illustrative', False),
            }
    return None
