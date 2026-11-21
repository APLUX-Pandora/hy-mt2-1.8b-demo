# Licensing

| Component | Terms |
|---|---|
| Application, examples, headers, Python binding and verification utility | [Apache-2.0](LICENSES/Apache-2.0.txt) |
| APLUX proprietary contributions in the SDK library | [Pandora Chinese](LICENSES/Pandora-Model-SDK.zh-CN.txt), [English translation](LICENSES/Pandora-Model-SDK.en.txt) |
| Compiled JSON support | [Third-party notices](NOTICE), [MIT and accompanying terms](LICENSES/nlohmann-json.txt) |
| Embedded Qualcomm Genie and tokenizer components | [SDK third-party notices](sdk/lib/THIRD_PARTY_NOTICES.txt) and [accompanying license texts](sdk/lib/LICENSES/) |
| Included Qualcomm QNN user-space runtime libraries | Unchanged files in [sdk/lib/qnn248/](sdk/lib/qnn248/), with supplier license and notices in that directory |
| External model weights and tokenizer data | Their accompanying model licenses; distributed separately |
| External device BSP/drivers, AidLMS, FastRPC, DSP firmware and basic system libraries | Their accompanying terms; device prerequisites, not bundled |

Pandora terms apply only to rights APLUX owns or may license. Binary form does not establish ownership of upstream components. Third-party permissions and required attribution remain intact. Application code does not become proprietary merely because it calls the SDK.

Keep the scoped SDK notices and full applicable license texts with standalone library deliveries. Model licenses and attribution accompany the separate model packages. Model weights and tokenizer data are supplied separately. Qualcomm Genie is linked into the SDK library, and QNN user-space libraries are included unchanged in sdk/lib/qnn248/. These bundled components retain their supplier and open-source terms; the Pandora agreement does not relicense them. Compatible BSP/drivers, AidLMS, FastRPC, DSP firmware and basic system libraries remain external device prerequisites. The SDK library contains compiled tokenizer components covered by its accompanying third-party notices.
