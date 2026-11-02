# Private file names do not isolate ELF symbols. Give SDK definitions a named
# version and bind backend-internal function calls to their own definitions.
function(sdk_elf_symbols target node)
  if(UNIX AND NOT APPLE AND BUILD_SHARED_LIBS)
    # GNU_UNIQUE data ignores RTLD_LOCAL and can coalesce with a foreign
    # protobuf/OR-Tools runtime even when this DSO has a named symbol version.
    if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
      target_compile_options(${target} PUBLIC
        "$<$<COMPILE_LANGUAGE:CXX>:-fno-gnu-unique>")
    endif()
    set(_map "${CMAKE_CURRENT_BINARY_DIR}/${target}.exports")
    get_target_property(_private ${target} OPTAGENT_SDK_PRIVATE_SYMBOLS)
    if(_private)
      string(JOIN "; " _private_patterns ${_private})
      file(WRITE "${_map}" "${node} { global: *; local: ${_private_patterns}; };\n")
    else()
      file(WRITE "${_map}" "${node} { global: *; };\n")
    endif()
    target_link_options(${target} PRIVATE
      "LINKER:--version-script=${_map}" "LINKER:-Bsymbolic-functions")
    set_property(TARGET ${target} APPEND PROPERTY LINK_DEPENDS "${_map}")
  endif()
endfunction()
