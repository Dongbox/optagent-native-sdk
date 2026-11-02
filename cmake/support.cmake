set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(SODIUM_DISABLE_TESTS ON CACHE BOOL "" FORCE)
set(SODIUM_MINIMAL ON CACHE BOOL "" FORCE)
add_subdirectory("${SDK_SODIUM_SOURCE_DIR}" sodium)
set_target_properties(sodium PROPERTIES
  EXPORT_NAME sodium
  INTERFACE_INCLUDE_DIRECTORIES "$<BUILD_INTERFACE:${SDK_SODIUM_SOURCE_DIR}/libsodium/src/libsodium/include>;$<INSTALL_INTERFACE:include>")
set(SKIP_INSTALL_ALL ON CACHE BOOL "" FORCE)
set(ZLIB_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
add_subdirectory("${SDK_ZLIB_SOURCE_DIR}" zlib)
if(TARGET zlib)
  set_target_properties(zlib PROPERTIES EXCLUDE_FROM_ALL TRUE)
endif()
set_target_properties(zlibstatic PROPERTIES EXPORT_NAME zlib
  INTERFACE_INCLUDE_DIRECTORIES "$<BUILD_INTERFACE:${SDK_ZLIB_SOURCE_DIR}>;$<BUILD_INTERFACE:${CMAKE_CURRENT_BINARY_DIR}/zlib>;$<INSTALL_INTERFACE:include>")
add_library(sdk_bzip2 STATIC)
foreach(source blocksort huffman crctable randtable compress decompress bzlib)
  target_sources(sdk_bzip2 PRIVATE "${SDK_BZIP2_SOURCE_DIR}/${source}.c")
endforeach()
set_target_properties(sdk_bzip2 PROPERTIES EXPORT_NAME bzip2)
target_include_directories(sdk_bzip2 PUBLIC
  "$<BUILD_INTERFACE:${SDK_BZIP2_SOURCE_DIR}>" "$<INSTALL_INTERFACE:include>")
install(TARGETS sodium zlibstatic sdk_bzip2 EXPORT OptAgentSupportTargets
  ARCHIVE DESTINATION lib LIBRARY DESTINATION lib RUNTIME DESTINATION bin)
install(DIRECTORY "${SDK_SODIUM_SOURCE_DIR}/libsodium/src/libsodium/include/"
  DESTINATION include FILES_MATCHING PATTERN "*.h" PATTERN private EXCLUDE)
install(FILES "${SDK_BZIP2_SOURCE_DIR}/bzlib.h" "${SDK_ZLIB_SOURCE_DIR}/zlib.h"
  "${CMAKE_CURRENT_BINARY_DIR}/zlib/zconf.h" DESTINATION include)
install(EXPORT OptAgentSupportTargets NAMESPACE OptAgentSupport::
  DESTINATION lib/cmake/OptAgentSupport)
install(FILES "${CMAKE_CURRENT_LIST_DIR}/OptAgentSupportConfig.cmake"
  DESTINATION lib/cmake/OptAgentSupport)
