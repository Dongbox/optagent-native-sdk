include_guard(GLOBAL)

function(sdk_toolchain_identity output)
  set(context "optagent-native-producer-v2;cxx20;pic")
  foreach(variable CMAKE_SYSTEM_NAME CMAKE_SYSTEM_PROCESSOR
      CMAKE_BUILD_TYPE CMAKE_C_COMPILER_ID CMAKE_C_COMPILER_VERSION
      CMAKE_CXX_COMPILER_ID CMAKE_CXX_COMPILER_VERSION
      CMAKE_CXX_IMPLICIT_INCLUDE_DIRECTORIES CMAKE_CXX_IMPLICIT_LINK_LIBRARIES
      CMAKE_CXX_IMPLICIT_LINK_DIRECTORIES
      CMAKE_C_FLAGS CMAKE_CXX_FLAGS CMAKE_C_FLAGS_RELEASE CMAKE_CXX_FLAGS_RELEASE
      CMAKE_C_FLAGS_DEBUG CMAKE_CXX_FLAGS_DEBUG CMAKE_C_FLAGS_RELWITHDEBINFO
      CMAKE_CXX_FLAGS_RELWITHDEBINFO CMAKE_MSVC_RUNTIME_LIBRARY
      CMAKE_OSX_ARCHITECTURES CMAKE_OSX_DEPLOYMENT_TARGET CMAKE_OSX_SYSROOT
      CMAKE_SYSROOT CMAKE_CXX_COMPILER_TARGET CMAKE_C_COMPILER_TARGET
      OPTAGENT_OPENBLAS_C_COMPILER
      OPTAGENT_SDK_SANITIZER OPTAGENT_NATIVE_LINKAGE)
    string(APPEND context "\n${variable}=${${variable}}")
  endforeach()
  if(OPTAGENT_OPENBLAS_C_COMPILER)
    file(SHA256 "${OPTAGENT_OPENBLAS_C_COMPILER}" checksum)
    string(APPEND context "\nblas-compiler-sha256=${checksum}")
  endif()
  foreach(compiler "${CMAKE_C_COMPILER}" "${CMAKE_CXX_COMPILER}")
    # macOS also exposes driver names as hard links. Compare the binary,
    # resource directory and detected defaults rather than the alias name.
    file(REAL_PATH "${compiler}" actual_compiler)
    get_filename_component(directory "${actual_compiler}" DIRECTORY)
    file(SHA256 "${compiler}" checksum)
    string(APPEND context "\ncompiler-directory=${directory}")
    string(APPEND context "\ncompiler-sha256=${checksum}")
  endforeach()
  foreach(variable VCToolsVersion WindowsSDKVersion UCRTVersion)
    string(APPEND context "\n${variable}=$ENV{${variable}}")
  endforeach()
  foreach(directory IN LISTS CMAKE_CXX_IMPLICIT_INCLUDE_DIRECTORIES)
    foreach(header __config __config_site bits/c++config.h yvals_core.h features.h)
      if(EXISTS "${directory}/${header}")
        file(SHA256 "${directory}/${header}" checksum)
        string(APPEND context "\nstdlib=${directory}/${header}:${checksum}")
      endif()
    endforeach()
  endforeach()
  if(APPLE)
    execute_process(COMMAND xcrun --show-sdk-path
      OUTPUT_VARIABLE sdk OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
    if(EXISTS "${sdk}/SDKSettings.json")
      file(SHA256 "${sdk}/SDKSettings.json" checksum)
      string(APPEND context "\nsdk=${sdk}:${checksum}")
    endif()
  endif()
  string(SHA256 identity "${context}")
  set(${output} "${identity}" PARENT_SCOPE)
endfunction()

