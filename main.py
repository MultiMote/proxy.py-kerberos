import proxy
from kerberos_auth import KerberosAuthPlugin

if __name__ == '__main__':
    proxy.main(plugins=[KerberosAuthPlugin])
