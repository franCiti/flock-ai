package ar.com.flockit.flockai.core.common;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ViewControllerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * The published documentation under {@code /docs} (plan 2.7, 6.3), public: an index page, Swagger UI
 * (springdoc) and the AsyncAPI documentation copied into {@code static/docs/asyncapi} by the build.
 */
@Configuration
public class DocsConfig implements WebMvcConfigurer {

    @Override
    public void addViewControllers(ViewControllerRegistry registry) {
        registry.addRedirectViewController("/docs", "/docs/");
        registry.addViewController("/docs/").setViewName("forward:/docs/index.html");
        // The AsyncAPI page loads its styles and scripts with relative paths: it needs the slash.
        registry.addRedirectViewController("/docs/asyncapi", "/docs/asyncapi/");
        registry.addViewController("/docs/asyncapi/").setViewName("forward:/docs/asyncapi/index.html");
    }
}
