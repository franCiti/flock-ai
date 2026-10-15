package ar.com.flockit.flockai.core.common;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

/** Application-wide beans: the clock (replaceable in tests) and scheduled tasks (D31). */
@Configuration
@EnableScheduling
public class AppConfig {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
