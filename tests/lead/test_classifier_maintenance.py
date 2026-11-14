from twdata.clients.classifier import classify
from twdata.clients.transport import HttpResult
from twdata.common.endpoints import ENDPOINTS


def test_maintenance_page_is_transient():
    body = "<html><title>網站維護中 - 臺灣證券交易所</title></html>".encode()
    res = classify(ENDPOINTS["twse.mi_qfiis"], HttpResult(200, {}, body))
    assert res.klass == "transient"
