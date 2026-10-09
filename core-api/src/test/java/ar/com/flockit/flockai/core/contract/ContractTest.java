package ar.com.flockit.flockai.core.contract;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.params.provider.Arguments.arguments;

import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;
import com.networknt.schema.Schema;
import com.networknt.schema.SchemaRegistry;
import com.networknt.schema.SpecificationVersion;
import java.io.IOException;
import java.lang.reflect.RecordComponent;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import tools.jackson.databind.DeserializationFeature;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * Compares the contract records with {@code contracts/} (D42): examples, JSON Schemas and enums. If the
 * contract changes and the records do not follow, one of these tests fails.
 */
class ContractTest {

    private static final Path CONTRACTS = Path.of(System.getProperty("contracts.dir", "../contracts"));

    /** Strict on purpose: a property of an example that the record does not have must fail. */
    private static final JsonMapper MAPPER = JsonMapper.builder()
            .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .build();

    private static final SchemaRegistry SCHEMAS = SchemaRegistry.withDefaultDialect(SpecificationVersion.DRAFT_7);

    /** Each message of the contract (its schema file and example folder) and its Java type. */
    private static final Map<String, Class<?>> MESSAGES = Map.of(
            "agent-request", AgentRequest.class,
            "agent-reply", AgentReply.class,
            "audit-entry", AuditEntry.class,
            "ingestion-job", IngestionJob.class,
            "ingestion-event", IngestionEvent.class);

    @Test
    void everyMessageOfTheContractHasAJavaType() throws IOException {
        try (Stream<Path> schemas = Files.list(CONTRACTS.resolve("schemas"));
                Stream<Path> examples = Files.list(CONTRACTS.resolve("examples"))) {
            assertThat(schemas.map(path -> path.getFileName().toString().replace(".v1.json", "")))
                    .containsExactlyInAnyOrderElementsOf(MESSAGES.keySet());
            assertThat(examples.map(path -> path.getFileName().toString()))
                    .containsExactlyInAnyOrderElementsOf(MESSAGES.keySet());
        }
    }

    @ParameterizedTest(name = "{0}/{1}")
    @MethodSource("examples")
    void exampleSurvivesARoundTripAndStaysValid(String message, String example) throws IOException {
        JsonNode original =
                MAPPER.readTree(CONTRACTS.resolve("examples").resolve(message).resolve(example));

        Object value = MAPPER.treeToValue(original, MESSAGES.get(message));
        JsonNode serialized = MAPPER.valueToTree(value);

        assertThat(serialized).isEqualTo(original);
        assertThat(schema(message).validate(serialized)).isEmpty();
    }

    @ParameterizedTest(name = "{0}")
    @MethodSource("recordsAndTheirSchemas")
    void recordHasExactlyThePropertiesOfItsSchema(Class<?> type, String message, String pointer) throws IOException {
        JsonNode root = readSchema(message);
        Set<String> components = Arrays.stream(type.getRecordComponents())
                .map(RecordComponent::getName)
                .collect(Collectors.toCollection(TreeSet::new));
        if (isVariant(type)) {
            components.add("type");
        }

        assertThat(components).isEqualTo(properties(root, root.at(pointer)));
    }

    @ParameterizedTest(name = "{0} {1}")
    @MethodSource("enumsAndTheirSchemas")
    void javaValuesMatchTheSchemaEnum(String message, String pointer, Set<String> javaValues) throws IOException {
        Set<String> schemaValues = new TreeSet<>();
        for (JsonNode value : readSchema(message).at(pointer).values()) {
            if (!value.isNull()) {
                schemaValues.add(value.stringValue());
            }
        }

        assertThat(javaValues).isEqualTo(schemaValues);
    }

    static Stream<Arguments> examples() throws IOException {
        List<Arguments> examples = new ArrayList<>();
        for (String message : new TreeSet<>(MESSAGES.keySet())) {
            try (Stream<Path> files = Files.list(CONTRACTS.resolve("examples").resolve(message))) {
                files.map(file -> file.getFileName().toString())
                        .sorted()
                        .forEach(file -> examples.add(arguments(message, file)));
            }
        }
        return examples.stream();
    }

    static Stream<Arguments> recordsAndTheirSchemas() {
        return Stream.of(
                arguments(AgentRequest.class, "agent-request", ""),
                arguments(AgentReply.AcceptedReply.class, "agent-reply", "/definitions/AcceptedReply"),
                arguments(AgentReply.TokenReply.class, "agent-reply", "/definitions/TokenReply"),
                arguments(AgentReply.FinalReply.class, "agent-reply", "/definitions/FinalReply"),
                arguments(AgentReply.ErrorReply.class, "agent-reply", "/definitions/ErrorReply"),
                arguments(AgentReply.Timing.class, "agent-reply", "/definitions/Timing"),
                arguments(PersonaRef.class, "agent-reply", "/definitions/PersonaRef"),
                arguments(Citation.class, "agent-reply", "/definitions/Citation"),
                arguments(Citation.class, "audit-entry", "/properties/citations/items"),
                arguments(AuditEntry.class, "audit-entry", ""),
                arguments(IngestionJob.class, "ingestion-job", ""),
                arguments(IngestionJob.JiraSource.class, "ingestion-job", "/definitions/JiraSource"),
                arguments(IngestionJob.ConfluenceSource.class, "ingestion-job", "/definitions/ConfluenceSource"),
                arguments(IngestionJob.SharePointSource.class, "ingestion-job", "/definitions/SharePointSource"),
                arguments(
                        IngestionJob.JiraScope.class,
                        "ingestion-job",
                        "/definitions/JiraSource/allOf/1/properties/scope"),
                arguments(
                        IngestionJob.ConfluenceScope.class,
                        "ingestion-job",
                        "/definitions/ConfluenceSource/allOf/1/properties/scope"),
                arguments(
                        IngestionJob.SharePointScope.class,
                        "ingestion-job",
                        "/definitions/SharePointSource/allOf/1/properties/scope"),
                arguments(IngestionEvent.StartedEvent.class, "ingestion-event", "/definitions/StartedEvent"),
                arguments(IngestionEvent.RejectedEvent.class, "ingestion-event", "/definitions/RejectedEvent"),
                arguments(
                        IngestionEvent.PersonaCompletedEvent.class,
                        "ingestion-event",
                        "/definitions/PersonaCompletedEvent"),
                arguments(
                        IngestionEvent.PersonaRemovedEvent.class,
                        "ingestion-event",
                        "/definitions/PersonaRemovedEvent"),
                arguments(IngestionEvent.CompletedEvent.class, "ingestion-event", "/definitions/CompletedEvent"),
                arguments(IngestionEvent.FailedEvent.class, "ingestion-event", "/definitions/FailedEvent"),
                arguments(IngestionEvent.PersonaSummary.class, "ingestion-event", "/definitions/PersonaSummary"),
                arguments(
                        IngestionEvent.SkippedFile.class,
                        "ingestion-event",
                        "/definitions/PersonaSummary/properties/skipped/items"),
                arguments(
                        IngestionEvent.SourceError.class,
                        "ingestion-event",
                        "/definitions/PersonaSummary/properties/sourceErrors/items"),
                arguments(IngestionEvent.Totals.class, "ingestion-event", "/definitions/Totals"));
    }

    static Stream<Arguments> enumsAndTheirSchemas() {
        return Stream.of(
                arguments(
                        "agent-reply", "/definitions/ReplyEnvelope/properties/type/enum", typeNames(AgentReply.class)),
                arguments("agent-reply", "/definitions/Outcome/enum", enumValues(Outcome.class)),
                arguments("agent-reply", "/definitions/ErrorCode/enum", enumValues(ErrorCode.class)),
                arguments("agent-reply", "/definitions/SourceType/enum", enumValues(SourceType.class)),
                arguments("audit-entry", "/properties/outcome/enum", enumValues(AuditEntry.AuditOutcome.class)),
                arguments("audit-entry", "/properties/errorCode/enum", enumValues(ErrorCode.class)),
                arguments("audit-entry", "/properties/flags/items/enum", enumValues(AuditEntry.Flag.class)),
                arguments(
                        "audit-entry",
                        "/properties/citations/items/properties/sourceType/enum",
                        enumValues(SourceType.class)),
                arguments("ingestion-job", "/properties/trigger/enum", enumValues(IngestionJob.Trigger.class)),
                arguments(
                        "ingestion-job",
                        "/definitions/SourceBase/properties/type/enum",
                        typeNames(IngestionJob.Source.class)),
                arguments(
                        "ingestion-event",
                        "/definitions/EventEnvelope/properties/type/enum",
                        typeNames(IngestionEvent.class)));
    }

    /** The properties an object schema allows, following {@code allOf} and local {@code $ref}s. */
    private static Set<String> properties(JsonNode root, JsonNode schema) {
        Set<String> names = new TreeSet<>(schema.path("properties").propertyNames());
        String ref = schema.path("$ref").asString("");
        if (ref.startsWith("#")) {
            names.addAll(properties(root, root.at(ref.substring(1))));
        }
        for (JsonNode part : schema.path("allOf").values()) {
            names.addAll(properties(root, part));
        }
        return names;
    }

    /** Whether the record is a variant of a message resolved by its {@code type} field. */
    private static boolean isVariant(Class<?> type) {
        return Arrays.stream(type.getInterfaces()).anyMatch(parent -> parent.isAnnotationPresent(JsonTypeInfo.class));
    }

    private static Set<String> typeNames(Class<?> sealedType) {
        return Arrays.stream(sealedType.getAnnotation(JsonSubTypes.class).value())
                .map(JsonSubTypes.Type::name)
                .collect(Collectors.toCollection(TreeSet::new));
    }

    private static Set<String> enumValues(Class<? extends Enum<?>> type) {
        Set<String> values = new TreeSet<>();
        for (Enum<?> constant : type.getEnumConstants()) {
            values.add(MAPPER.convertValue(constant, String.class));
        }
        return values;
    }

    private static JsonNode readSchema(String message) throws IOException {
        return MAPPER.readTree(CONTRACTS.resolve("schemas").resolve(message + ".v1.json"));
    }

    private static Schema schema(String message) throws IOException {
        return SCHEMAS.getSchema(readSchema(message));
    }
}
