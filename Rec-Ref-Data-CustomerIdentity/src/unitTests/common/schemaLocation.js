const schemaLocation=
{
  type: "object",
  properties: {
    customerLocationReference: {
      type: "object",
      properties: {
        location: {
          type: "array",
          items: {
            type: "object",
            properties: {
              locationAddressType: {
                type: "string"
              },
              locationInegiCode: {
                type: "string"
              },
              street: {
                type: "object",
                properties: {
                  streetNumber: {
                    type: "string"
                  },
                  streetName: {
                    type: "string"
                  }
                },
                required: ["streetNumber", "streetName"]
              },
              neighborhood: {
                type: "string"
              },
              locationDescription: {
                type: "string"
              },
              locationReferencePoint: {
                type: "string"
              },
              locationObservations: {
                type: "string"
              },
              neighborhoodNumber: {
                type: "string"
              },
              country: {
                type: "object",
                properties: {
                  code: {
                    type: "string"
                  }
                },
                required: ["code"]
              },
              countyDistrict: {
                type: "object",
                properties: {
                  code: {
                    type: "string"
                  },
                  name: {
                    type: "string"
                  },
                  inegiCode: {
                    type: "string"
                  }
                },
                required: ["code", "name", "inegiCode"]
              },
              postalCode: {
                type: "string"
              },
              city: {
                type: "object",
                properties: {
                  code: {
                    type: "string"
                  }
                },
                required: ["code"]
              },
              province: {
                type: "object",
                properties: {
                  name: {
                    type: "string"
                  },
                  code:{
                    type:"string"
                  }
                },
                required: ["name","code"]
              },
              cityNumber:{
                type:"number"
              },
              state: {
                type: "object",
                properties: {
                  code: {
                    type: "string"
                  },
                  inegiCode: {
                    type: "string"
                  }
                },
                required: ["code", "inegiCode"]
              },
              externalHouseNumber: {
                type: "string"
              },
              internalHouseNumber: {
                type: "string"
              },
              houseNumber: {
                type: "string"
              },
              cardinalPoint: {
                type: "string"
              },
              sector: {
                type: "string"
              },
              block: {
                type: "string"
              },
              stage: {
                type: "string"
              },
              lot: {
                type: "string"
              },
              building: {
                type: "string"
              },
              entryPoint: {
                type: "string"
              },
              isHousingUnit: {
                type: "boolean"
              }
            },
            required: [
              "locationAddressType",
              "locationInegiCode",
              "street",
              "neighborhood",
              "locationDescription",
              "locationReferencePoint",
              "locationObservations",
              "neighborhoodNumber",
              "country",
              "countyDistrict",
              "postalCode",
              "city",
              "cityNumber",
              "province",
              "state",
              "externalHouseNumber",
              "internalHouseNumber",
              "houseNumber",
              "cardinalPoint",
              "sector",
              "block",
              "stage",
              "lot",
              "building",
              "entryPoint",
              "isHousingUnit"
            ]
          }
        },
        partyReference: {
          type: "object",
          properties: {
            referenceId: {
              type: "string"
            },
            referenceIdCoppel: {
              type: "string"
            },
            contactPoint: {
              type: "array",
              minItems: 3,
              maxItems:3,
              items: {
                type: "object",
                properties: {
                  contactPointType: {
                    type: "string"
                  },
                  contactPointValue: {
                    type: "string"
                  },
                  contactPointDetail: {
                    type: "string"
                  },
                  contactPointStatus: {
                    type: "string"
                  }
                },
                required: [
                  "contactPointType",
                  "contactPointValue",
                  "contactPointDetail",
                  "contactPointStatus"
                ]
              }
            }
          },
          required: [
            "referenceId",
            "referenceIdCoppel",
            "contactPoint"
          ]
        },
        sequence: {
          type: "string"
        },
        user: {
          type: "string"
        },
        dateInsert: {
          type: "string"
        },
        companyReference: {
          type: "string"
        },
        option: {
          type: "string"
        },
        operationType: {
          type: "string"
        }
      },
      required: [
        "location",
        "partyReference",
        "sequence",
        "user",
        "dateInsert",
        "companyReference",
        "option",
        "operationType"
      ]
   },

  },
  required: [
    "customerLocationReference"
  ]
};

module.exports = schemaLocation;