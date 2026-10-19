{
    'name': 'MRP Approval Flow',
    'version': '19.0.1.0.0',
    'summary': 'Approval step before manufacturing orders can be started or finished',
    'category': 'Manufacturing',
    'author': 'ccihanbeyoglu',
    'license': 'LGPL-3',
    'depends': ['mrp'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'security/rules.xml',
        'views/mrp_production_views.xml',
    ],
    'installable': True,
    'application': False,
}
