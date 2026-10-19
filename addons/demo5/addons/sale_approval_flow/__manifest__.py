{
    'name': 'Sale Approval Flow',
    'version': '19.0.1.0.0',
    'summary': 'Approval before large sales orders can be confirmed, plus special instructions on the order PDF',
    'author': 'ccihanbeyoglu',
    'license': 'LGPL-3',
    'category': 'Sales',
    'depends': ['sale'],
    'data': [
        'security/security.xml',
        'data/config_parameter.xml',
        'views/sale_order_views.xml',
        'report/sale_order_report.xml',
    ],
    'installable': True,
    'application': False,
}
