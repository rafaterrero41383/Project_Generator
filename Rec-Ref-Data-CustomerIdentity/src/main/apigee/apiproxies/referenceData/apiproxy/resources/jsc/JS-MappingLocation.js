/*jshint esversion: 8 */

const requestHeaderConsumerRequestId = 'request.header.consumerRequestId';
const requestHeaderToken = 'request.header.token';
const requestContent = 'request.content';

const consumerRequestId = context.getVariable(requestHeaderConsumerRequestId);
const token = context.getVariable(requestHeaderToken);
const body = JSON.parse(context.getVariable(requestContent));

const newBody = {
  customerLocationReference: {
    location: body.customerLocationReference.location.map(location => ({
      locationAddressType: location.locationAddressType,
      locationInegiCode: location.locationInegiCode,
      street: {
        streetNumber: location.street.streetNumber,
        streetName: location.street.streetName
      },
      neighborhood: location.neighborhood,
      locationDescription: location.locationDescription,
      locationReferencePoint: location.locationReferencePoint,
      locationObservations: location.locationObservations,
      neighborhoodNumber: location.neighborhoodNumber,
      cityNumber:location.cityNumber,
      country: {
        code: location.country.code
      },
      countyDistrict: {
        code: location.countyDistrict.code,
        name: location.countyDistrict.name,
        inegiCode: location.countyDistrict.inegiCode
      },
      postalCode: location.postalCode,
      city: {
        code: location.city.code
      },
      province: {
        name: location.province.name,
        code: location.province.code
      },
      state: {
        code: location.state.code,
        inegiCode: location.state.inegiCode
      },
      externalHouseNumber: location.externalHouseNumber,
      internalHouseNumber: location.internalHouseNumber,
      houseNumber: location.houseNumber,
      cardinalPoint: location.cardinalPoint,
      sector: location.sector,
      block: location.block,
      stage: location.stage,
      lot: location.lot,
      building: location.building,
      entryPoint: location.entryPoint,
      isHousingUnit: location.isHousingUnit
    })),
    partyReference: {
      referenceId: body.customerLocationReference.partyReference.referenceId,
      referenceIdCoppel: body.customerLocationReference.partyReference.referenceIdCoppel,
      contactPoint: body.customerLocationReference.partyReference.contactPoint.map(contact => ({
        contactPointType: contact.contactPointType,
        contactPointValue: contact.contactPointValue,
        contactPointDetail: contact.contactPointDetail,
        contactPointStatus: contact.contactPointStatus
      }))
    }, 
  sequence: body.customerLocationReference.sequence,
  user: body.customerLocationReference.user,
  dateInsert: body.customerLocationReference.dateInsert,
  companyReference: body.customerLocationReference.companyReference,
  option: body.customerLocationReference.option,
  operationType: body.customerLocationReference.operationType
}
};

context.setVariable(requestHeaderConsumerRequestId, consumerRequestId);
context.setVariable(requestHeaderToken, token);
context.setVariable(requestContent, JSON.stringify(newBody));