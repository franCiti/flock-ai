package ar.com.flockit.flockai.core.common;

import java.util.Properties;
import org.postgresql.ssl.WrappedFactory;
import org.springframework.boot.ssl.SslBundle;
import org.springframework.boot.ssl.pem.PemSslStoreBundle;
import org.springframework.boot.ssl.pem.PemSslStoreDetails;

/**
 * TLS for the PostgreSQL driver from the PEM files of the connection URL ({@code sslcert},
 * {@code sslkey}, {@code sslrootcert}), read the same way Spring reads them for Kafka.
 *
 * <p>pgjdbc's own reader refuses, on Windows, a private key that the Administrators group can read,
 * which is the default for any file of a user. The key is still only used by this process; the
 * server is still verified: its certificate against the flock-ai CA, and its name by pgjdbc
 * ({@code sslmode=verify-full}). Selected with {@code sslfactory} in the URL
 * ({@code application-mtls.yml}).
 */
public class PemSslSocketFactory extends WrappedFactory {

    public PemSslSocketFactory(Properties info) {
        PemSslStoreDetails keyStore =
                PemSslStoreDetails.forCertificate(location(info, "sslcert")).withPrivateKey(location(info, "sslkey"));
        PemSslStoreDetails trustStore = PemSslStoreDetails.forCertificate(location(info, "sslrootcert"));
        factory = SslBundle.of(new PemSslStoreBundle(keyStore, trustStore))
                .createSslContext()
                .getSocketFactory();
    }

    private static String location(Properties info, String property) {
        String path = info.getProperty(property);
        if (path == null || path.isBlank()) {
            throw new IllegalArgumentException("missing " + property + " in the PostgreSQL URL");
        }
        return "file:" + path;
    }
}
