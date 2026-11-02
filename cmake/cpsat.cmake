add_subdirectory("${SDK_CPSAT_SOURCE_DIR}/cmake/optagent-sdk" cpsat)
include("${CMAKE_CURRENT_LIST_DIR}/elf-symbols.cmake")
sdk_elf_symbols(optagent_cpsat OPTAGENT_NATIVE_1)
