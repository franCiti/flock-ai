package ar.com.flockit.flockai.core.support;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;

/**
 * A Spring Boot test with the whole application against ephemeral PostgreSQL and Kafka
 * ({@link TestInfrastructure}), profile {@code test} (no TLS).
 */
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@SpringBootTest
@ActiveProfiles("test")
@Import(TestInfrastructure.class)
public @interface IntegrationTest {}
