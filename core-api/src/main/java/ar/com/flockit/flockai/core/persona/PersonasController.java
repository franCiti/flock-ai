package ar.com.flockit.flockai.core.persona;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.List;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** The personas the web app can ask (spec HU10.2, plan 6.3). */
@RestController
@RequestMapping(value = "/api/personas", produces = MediaType.APPLICATION_JSON_VALUE)
@Tag(name = "personas", description = "Virtual personas")
public class PersonasController {

    private final PersonaViewRepository personas;

    public PersonasController(PersonaViewRepository personas) {
        this.personas = personas;
    }

    @GetMapping
    @Operation(summary = "Available personas, by display name")
    public List<PersonaViewRepository.PersonaView> list() {
        return personas.findAll();
    }
}
