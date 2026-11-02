# Private file names do not isolate ELF symbols. Give SDK definitions a named
# version and bind backend-internal function calls to their own definitions.
function(sdk_elf_symbols target node)
  if(UNIX AND NOT APPLE AND BUILD_SHARED_LIBS)
    set(_map "${CMAKE_CURRENT_BINARY_DIR}/${target}.exports")
    file(WRITE "${_map}" "${node} { global: *; };\n")
    target_link_options(${target} PRIVATE
      "LINKER:--version-script=${_map}" "LINKER:-Bsymbolic-functions")
    set_property(TARGET ${target} APPEND PROPERTY LINK_DEPENDS "${_map}")
  endif()
endfunction()
