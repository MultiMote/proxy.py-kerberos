import logging
from typing import Optional, Any, Dict

import kerberos
from proxy.http import httpHeaders, httpStatusCodes
from proxy.http.exception import HttpRequestRejected
from proxy.http.parser import HttpParser
from proxy.http.proxy import HttpProxyBasePlugin
from proxy.common.flag import flags


logger = logging.getLogger(__name__)


flags.add_argument(
    '--krb-service-name',
    type=str,
    default='HTTP',
    help='A string containing the Kerberos service type for the server',
)


flags.add_argument(
    '--krb-hostname',
    type=str,
    required=True,
    help='A string containing the hostname of the server',
)


def _err_407():
    return HttpRequestRejected(
        status_code=httpStatusCodes.PROXY_AUTH_REQUIRED,
        headers={b'Proxy-Authenticate': b'Negotiate'},
        reason=b'Proxy Authentication Required')


def _err_401():
    return HttpRequestRejected(
        status_code=httpStatusCodes.UNAUTHORIZED,
        reason=b'Unauthorized')


def _err_500():
    return HttpRequestRejected(
        status_code=httpStatusCodes.INTERNAL_SERVER_ERROR,
        reason=b'Server error')


class KerberosAuthPlugin(HttpProxyBasePlugin):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.krb_username = None
        self.service_name = f"{self.flags.krb_service_name}@{self.flags.krb_hostname}"

        # verify keytab
        kerberos.getServerPrincipalDetails(
            self.flags.krb_service_name,
            self.flags.krb_hostname
        )

    def before_upstream_connection(self, request: HttpParser) -> Optional[HttpParser]:
        if request.headers:
            if httpHeaders.PROXY_AUTHORIZATION not in request.headers:
                raise _err_407()

            parts = request.headers[httpHeaders.PROXY_AUTHORIZATION][1].split()

            if len(parts) != 2 or parts[0].lower() != b'negotiate':
                raise _err_407()

            token = parts[1].decode('ascii')

            rc, context = kerberos.authGSSServerInit(self.service_name)

            if rc != kerberos.AUTH_GSS_COMPLETE:
                kerberos.authGSSServerClean(context)
                raise _err_500()

            try:
                rc = kerberos.authGSSServerStep(context, token)
            except kerberos.GSSError as e:
                logger.critical(e, exc_info=True)
                kerberos.authGSSServerClean(context)
                raise _err_500() from e

            if rc == kerberos.AUTH_GSS_COMPLETE:
                kerberos_user = kerberos.authGSSServerUserName(context)
                self.krb_username = kerberos_user
                return request

            logger.warning("authGSSServerStep rc = %d", rc)
            kerberos.authGSSServerClean(context)
            raise _err_401()

        raise _err_401()

    def on_access_log(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if self.krb_username:
            context.update({
                'client_ip': self.krb_username
            })
        return context
